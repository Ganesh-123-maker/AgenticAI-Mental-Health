from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import math
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

try:
    from jinja2 import Template
except ImportError:  # pragma: no cover
    Template = None  # type: ignore[assignment]

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore[assignment]

try:
    from google import genai
except ImportError:  # pragma: no cover
    genai = None

try:
    import torch
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]

try:
    from src.shared.file_utils import resolve_path
except ModuleNotFoundError:  # pragma: no cover - supports PYTHONPATH=src execution style
    from shared.file_utils import resolve_path

from .backends.base import ModelBackend
from .core.schemas import RuntimeConfig
from .utils import extract_tag_content


class StageMapDict(dict):
    def __getitem__(self, key: str) -> int:
        return self.get(key, 1)

    def get(self, key: Any, default: Any = 1) -> Any:
        if key in self:
            return super().get(key, default)
        k = str(key).lower()
        if any(term in k for term in ("consolidation", "relapse", "prevention", "termination", "3")):
            return 3
        if any(term in k for term in ("intervention", "core", "behavioral", "cognitive", "2")):
            return 2
        if any(term in k for term in ("problem", "conceptualization", "goal", "setting", "assessment", "1")):
            return 1
        return default


STAGE_MAP: Dict[str, int] = StageMapDict({
    "Problem Conceptualization and Goal Setting": 1,
    "Core Cognitive and Behavioral Interventions": 2,
    "Consolidation and Relapse Prevention": 3,
    "Assessment": 1,
    "Intervention": 2,
    "Consolidation": 3,
    "Termination": 3,
    "Stage 1": 1,
    "Stage 2": 2,
    "Stage 3": 3,
})
DEFAULT_SECTS = ["cbt", "bt", "pdt", "het", "pmt"]


@dataclass
class LoadedSkillStage:
    meta: Dict[str, Dict[str, Any]]
    micro: Dict[str, Dict[str, Any]]
    leaf: Dict[str, Dict[str, Any]]


class SkillManager:
    def __init__(self, backend: ModelBackend, runtime_config: RuntimeConfig, logger: Optional[logging.Logger] = None):
        self._backend = backend
        self._runtime = runtime_config
        self._logger = logger or logging.getLogger(self.__class__.__name__)

        self.skill_lib: Dict[str, Dict[str, LoadedSkillStage]] = {}
        self._embedding_client: Any = None

        self._select_system_prompt = ""
        self._select_user_prompt = ""
        self._rewrite_system_prompt = ""
        self._rewrite_user_prompt = ""

    async def _ensure_embeddings_for_all(self, micro_lib: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], bool]:
        if not micro_lib:
            return micro_lib, False

        updated = False
        missing_merge_ids = []
        missing_retrieve_ids = []

        # 1. Scan for missing embeddings and unify format
        for sid, skill in micro_lib.items():
            # Ensure list format for downstream processing
            m_vec = self._vector_to_list(skill.get("embedding_to_merge"))
            r_vec = self._vector_to_list(skill.get("embedding_to_retrive"))

            if m_vec is None:
                missing_merge_ids.append(sid)
            else:
                skill["embedding_to_merge"] = m_vec # Store uniformly as list

            if r_vec is None:
                missing_retrieve_ids.append(sid)
            else:
                skill["embedding_to_retrive"] = r_vec

        # 2. Backfill merge embeddings

        # 1b. Guard against stale vectors from a different embedding model.
        # Stored vectors (e.g. 1024-dim bge-m3) must never be mixed with a newly
        # configured dimensionality (e.g. 768-dim gemini-embedding-001): cosine
        # similarity silently returns -1.0 on dimension mismatch. Re-embed all.
        expected_dim = max(1, int(self._runtime.psychagent_embedding_dimensions))
        stale_found = False
        for _sid, _skill in micro_lib.items():
            for _field in ("embedding_to_merge", "embedding_to_retrive"):
                _vec = _skill.get(_field)
                if isinstance(_vec, list) and _vec and len(_vec) != expected_dim:
                    stale_found = True
                    break
            if stale_found:
                break
        if stale_found:
            self._logger.warning(
                "Stored skill embeddings have dimension != %d (embedding model/dim changed); "
                "re-embedding all %d skills with model '%s'.",
                expected_dim, len(micro_lib), self._runtime.psychagent_embedding_model,
            )
            for _sid in micro_lib:
                micro_lib[_sid]["embedding_to_merge"] = None
                micro_lib[_sid]["embedding_to_retrive"] = None
            missing_merge_ids = list(micro_lib.keys())
            missing_retrieve_ids = list(micro_lib.keys())

        if missing_merge_ids:
            self._logger.info(f"Backfilling {len(missing_merge_ids)} merge embeddings...")
            texts = [
                json.dumps(
                    {k: v for k, v in micro_lib[sid].items()
                     if k in {"skill_id", "skill_name", "skill_description", "trigger", "when_to_use", "parent_ids"}},
                    ensure_ascii=False
                )
                for sid in missing_merge_ids
            ]
            embs = await self._embed_by_api(texts, task_type="RETRIEVAL_DOCUMENT")
            for sid, emb in zip(missing_merge_ids, embs):
                micro_lib[sid]["embedding_to_merge"] = emb
            updated = True

        # 3. Backfill retrieve embeddings
        if missing_retrieve_ids:
            self._logger.info(f"Backfilling {len(missing_retrieve_ids)} retrieve embeddings...")
            texts = [
                f"Trigger:{micro_lib[sid].get('trigger', '')}\nWhen_to_Use:{micro_lib[sid].get('when_to_use', '')}"
                for sid in missing_retrieve_ids
            ]
            embs = await self._embed_by_api(texts, task_type="RETRIEVAL_DOCUMENT")
            for sid, emb in zip(missing_retrieve_ids, embs):
                micro_lib[sid]["embedding_to_retrive"] = emb
            updated = True

        return micro_lib, updated

    async def load_library(self) -> None:
        self._load_prompts()

        sects = self._normalize_sects(self._runtime.psychagent_skill_sects)
        base_dir = resolve_path(self._runtime.psychagent_skill_base_dir)

        for sect in sects:
            sect_stages: Dict[str, LoadedSkillStage] = {}
            for stage_idx in (1, 2, 3):
                stage_key = f"stage{stage_idx}"
                stage_dir = base_dir / sect / stage_key
                meta = self._load_json_dict(stage_dir / "meta_skills.json")
                micro = self._load_micro_skills(stage_dir)
                leaf = self.get_leaf_nodes(meta)
                sect_stages[stage_key] = LoadedSkillStage(meta=meta, micro=micro, leaf=leaf)
            self.skill_lib[sect] = sect_stages

        self._logger.info("Skill library loaded, starting embedding check and backfill...")

        # Iterate over all sects and stages
        for sect, stages in self.skill_lib.items():
            for stage_key, loaded_stage in stages.items():
                # Check whether micro_skills lack embeddings
                # Note: Call newly defined async completion method
                updated_micro, is_updated = await self._ensure_embeddings_for_all(loaded_stage.micro)

                if is_updated:
                    self._logger.info(f"Updating embeddings for {sect} {stage_key}...")
                    loaded_stage.micro = updated_micro

                    save_dir = resolve_path(self._runtime.psychagent_skill_base_dir) / sect / stage_key
                    # Never overwrite the original artifacts: persist to the
                    # provenance-keyed store for the configured embedding space.
                    keyed_name = f"micro_skills.{self._embedding_store_key()}.pt"
                    save_path = save_dir / keyed_name
                    base_pt = save_dir / "micro_skills.pt"
                    source_hash = self._sha256_file(base_pt) if base_pt.exists() else ""
                    payload = dict(loaded_stage.micro)
                    payload["_provenance"] = self._build_provenance(
                        source_hash, len(loaded_stage.micro)
                    )

                    # Atomic write: temp file then rename, avoiding a torn store.
                    if torch is not None:
                        loop = asyncio.get_running_loop()

                        def _atomic_save() -> None:
                            tmp = save_path.with_suffix(".pt.tmp")
                            torch.save(payload, str(tmp))
                            os.replace(str(tmp), str(save_path))

                        await loop.run_in_executor(None, _atomic_save)
                        self._logger.info(f"Saved updated skills to {save_path}")

        self._logger.info("Skill library embedding check complete.")

    async def corse_filter(
        self,
        sect: str,
        session_goals: Any,
        stage: int | str,
        n: int = 20,
        model_kwgs: Optional[Dict[str, Any]] = None,
        saved: bool = False,
        rerank: bool = False,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Tuple[str, str]], Dict[str, Any]]:
        del saved, rerank
        stage_idx = self._resolve_stage(stage)
        stage_key = f"stage{stage_idx}"
        lib = self.skill_lib.get(sect, {})
        loaded_stage = lib.get(stage_key)
        if loaded_stage is None:
            raise ValueError(f"skill stage missing: sect={sect} stage={stage_key}")

        leaf_skills = loaded_stage.leaf
        if not leaf_skills:
            return [], [], [], {"messages": []}

        ids: List[Tuple[str, str]] = []
        select_system_prompt = self._select_system_prompt
        select_user_prompt = self._select_user_prompt
        response = ""

        try:
            if self._select_system_prompt and self._select_user_prompt:
                skill_to_filter = {
                    k: {ik: iv for ik, iv in v.items() if ik not in {"parent_ids", "embedding_to_merge", "embedding_to_retrive"}}
                    for k, v in leaf_skills.items()
                }
                select_system_prompt = self._render_template(self._select_system_prompt, number=n)
                select_user_prompt = self._render_template(
                    self._select_user_prompt,
                    session_goals=session_goals,
                    skills_library=skill_to_filter,
                )
                response = await self.llm_response(select_system_prompt, select_user_prompt, model_kwgs=model_kwgs)
                parsed = self._extract_json_object(response)
                raw_ids = parsed.get("skill_id", []) if isinstance(parsed, dict) else []
                ids = [(sect, str(sid)) for sid in raw_ids]
        except Exception as exc:  # pragma: no cover - defensive fallback
            self._logger.warning("coarse_filter parse failed, fallback to default top skills: %s", exc)

        if not ids:
            fallback_ids = list(leaf_skills.keys())[:n]
            ids = [(sect, str(sid)) for sid in fallback_ids]

        meta_skills, meta_wo_embed = self.find_skill_by_id(stage_idx, ids)

        res = {
            "messages": [
                {"role": "system", "content": select_system_prompt},
                {"role": "user", "content": select_user_prompt},
                {"role": "assistant", "content": response},
            ]
        }
        return meta_skills, meta_wo_embed, ids, res

    async def retrive(
        self,
        sect: str,
        query: str,
        session_stage: int | str,
        session_goals: Any,
        diag_hist: List[Dict[str, str]],
        top_n: int = 20,
        top_k: int = 5,
        threshold: Optional[float] = None,
        candidate_skills: Optional[List[Dict[str, Any]]] = None,
        model_kwgs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        stage_idx = self._resolve_stage(session_stage)

        if candidate_skills is None:
            meta_skills, _, _, _ = await self.corse_filter(
                sect=sect,
                session_goals=session_goals,
                stage=stage_idx,
                n=top_n,
                model_kwgs=model_kwgs,
            )
            candidate_skills = []
            for skill in meta_skills:
                candidate_skills.extend(skill.get("micro_skills", []))

        if not candidate_skills:
            return [], {}

        rewritten_query, res_rewrite = await self.rewrite(
            sect=sect,
            query=query,
            stage=stage_idx,
            session_goals=session_goals,
            diag_hist=diag_hist,
            model_kwgs=model_kwgs,
        )
        query_text = extract_tag_content(rewritten_query, "response") or rewritten_query
        query_embedding = (await self._embed_by_api([query_text], task_type="RETRIEVAL_QUERY"))[0]

        await self._ensure_embeddings_for_candidates(candidate_skills)

        scored: List[Tuple[float, int]] = []
        for idx, skill in enumerate(candidate_skills):
            vec = self._vector_to_list(skill.get("embedding_to_retrive"))
            if not vec:
                continue
            score = self._cosine_similarity(query_embedding, vec)
            if threshold is not None and score < threshold:
                continue
            scored.append((score, idx))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[:top_k]

        retrieved: List[Dict[str, Any]] = []
        for score, idx in selected:
            skill = copy.deepcopy(candidate_skills[idx])
            skill["similarity"] = float(score)
            skill.pop("embedding_to_merge", None)
            skill.pop("embedding_to_retrive", None)
            retrieved.append(skill)

        return retrieved, res_rewrite

    async def rewrite(
        self,
        sect: str,
        query: str,
        stage: int | str,
        session_goals: Any,
        diag_hist: List[Dict[str, str]],
        model_kwgs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        del sect
        rewrite_system_prompt = self._rewrite_system_prompt
        rewrite_user_prompt = self._rewrite_user_prompt

        if not rewrite_user_prompt:
            return query, {"messages": []}

        rendered_user = self._render_template(
            rewrite_user_prompt,
            Session_Goals=session_goals,
            Dialogue_History=diag_hist if diag_hist else "No dialogue history.",
            Current_Client_Query=query,
            stage=stage,
            Treatment_Structure="General",
        )
        response = await self.llm_response(rewrite_system_prompt, rendered_user, model_kwgs=model_kwgs)
        res = {
            "messages": [
                {"role": "system", "content": rewrite_system_prompt},
                {"role": "user", "content": rendered_user},
                {"role": "assistant", "content": response},
            ]
        }
        return response, res

    async def llm_response(
        self,
        template: str,
        input_text: str,
        model_kwgs: Optional[Dict[str, Any]] = None,
    ) -> str:
        del model_kwgs
        messages = [
            {"role": "system", "content": template},
            {"role": "user", "content": input_text},
        ]
        return await self._backend.chat_text(messages=messages)

    def find_skill_by_id(self, stage: int, skill_ids: Sequence[Tuple[str, str]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        result: List[Dict[str, Any]] = []
        result_wo_embed: List[Dict[str, Any]] = []
        stage_key = f"stage{stage}"

        for sect, meta_id in skill_ids:
            stage_data = self.skill_lib.get(sect, {}).get(stage_key)
            if stage_data is None:
                continue

            meta_skills = stage_data.meta
            micro_skills = stage_data.micro
            meta_item = meta_skills.get(meta_id)
            if not meta_item:
                continue

            parent_prefix = list(meta_item.get("parent_ids", []))
            children: List[Dict[str, Any]] = []
            for micro_item in micro_skills.values():
                micro_parent_ids = list(micro_item.get("parent_ids", []))
                if (
                    len(micro_parent_ids) == len(parent_prefix) + 1
                    and micro_parent_ids[:-1] == parent_prefix
                    and micro_parent_ids[-1] == str(micro_item.get("skill_id", ""))
                ):
                    children.append(micro_item)

            concat_meta = [str(meta_skills[aid].get("skill_name", "")) for aid in parent_prefix if aid in meta_skills]
            meta_str = "\n".join([x for x in concat_meta if x])

            children_wo_embed: List[Dict[str, Any]] = []
            for skill in children:
                children_wo_embed.append(
                    {k: v for k, v in skill.items() if k not in {"embedding_to_merge", "embedding_to_retrive"}}
                )

            result.append({"sect": sect, "meta_skill": meta_str, "micro_skills": children})
            result_wo_embed.append({"sect": sect, "meta_skill": meta_str, "micro_skills": children_wo_embed})

        return result, result_wo_embed

    def get_leaf_nodes(self, skills):
        """CPU Bound logic, fast enough to keep sync."""
        all_skill_ids = set(skills.keys())
        non_leaf_skill_ids = set()
        for skill_id, skill_data in skills.items():
            for other_skill_id, other_skill_data in skills.items():
                if skill_id == other_skill_id: continue
                if skill_id in other_skill_data.get("parent_ids", []):
                    non_leaf_skill_ids.add(skill_id)
                    break
        leaf_nodes = [
            (skill_id, skill_data) for skill_id, skill_data in skills.items()
            if skill_id not in non_leaf_skill_ids
        ]
        return dict(leaf_nodes)

    async def _ensure_embeddings_for_candidates(self, candidate_skills: List[Dict[str, Any]]) -> None:
        missing_retrieve: List[Dict[str, Any]] = []
        missing_merge: List[Dict[str, Any]] = []

        for skill in candidate_skills:
            if self._vector_to_list(skill.get("embedding_to_retrive")) is None:
                missing_retrieve.append(skill)
            if self._vector_to_list(skill.get("embedding_to_merge")) is None:
                missing_merge.append(skill)

        if missing_merge:
            merge_texts = [
                json.dumps(
                    {
                        k: v
                        for k, v in skill.items()
                        if k in {"skill_id", "skill_name", "skill_description", "trigger", "when_to_use", "parent_ids"}
                    },
                    ensure_ascii=False,
                )
                for skill in missing_merge
            ]
            merge_vecs = await self._embed_by_api(merge_texts, task_type="RETRIEVAL_DOCUMENT")
            for skill, vec in zip(missing_merge, merge_vecs):
                skill["embedding_to_merge"] = vec

        if missing_retrieve:
            retrieve_texts = [
                f"Trigger:{skill.get('trigger', '')}\nWhen_to_Use:{skill.get('when_to_use', '')}"
                for skill in missing_retrieve
            ]
            retrieve_vecs = await self._embed_by_api(retrieve_texts, task_type="RETRIEVAL_DOCUMENT")
            for skill, vec in zip(missing_retrieve, retrieve_vecs):
                skill["embedding_to_retrive"] = vec

    def _is_offline_embedding_mode(self) -> bool:
        """True when the run is explicitly offline.

        The signal is the backend instance itself: backends that never touch
        the network declare ``is_offline = True`` (see DummyBackend). This is
        checked BEFORE any API-key lookup or SDK construction so offline tests
        are hermetic even if embedding keys happen to be set in the
        environment. A live backend never degrades to offline silently.
        """
        backend = getattr(self, "_backend", None)
        return bool(getattr(backend, "is_offline", False))

    @staticmethod
    def _is_retryable_embedding_error(exc: BaseException) -> bool:
        """Fail fast on auth/invalid-request errors; retry transient ones."""
        code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        try:
            code_int = int(code) if code is not None else None
        except (TypeError, ValueError):
            code_int = None
        if code_int in (400, 401, 403, 404):
            return False
        msg = str(exc).lower()
        for token in ("unauthorized", "forbidden", "invalid api key", "api key not valid",
                      "permission denied", "bad request", "not found"):
            if token in msg:
                return False
        return True

    @staticmethod
    def _retry_after_seconds(exc: BaseException) -> Optional[float]:
        """Extract Retry-After (seconds) from a provider error, if present."""
        headers = getattr(exc, "headers", None)
        if headers is None:
            resp = getattr(exc, "response", None)
            headers = getattr(resp, "headers", None) if resp is not None else None
        if headers:
            try:
                get = getattr(headers, "get", None)
                if callable(get):
                    ra = get("retry-after") or get("Retry-After")
                    if ra is not None:
                        return max(0.0, float(str(ra).split(",")[0].strip()))
            except (TypeError, ValueError):
                pass
        return None

    @staticmethod
    def _is_rate_limit_error(exc: BaseException) -> bool:
        code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        try:
            if int(code) == 429:
                return True
        except (TypeError, ValueError):
            pass
        return "rate limit" in str(exc).lower() or "429" in str(exc)

    def _backoff_delay(self, attempt: int, sleep_sec: float, exc: BaseException) -> float:
        """Exponential backoff with jitter, honoring Retry-After; capped at 60s."""
        base = max(0.0, float(sleep_sec)) * (2.0 ** max(0, attempt - 1))
        delay = base + random.uniform(0, base * 0.25 + 0.001)
        retry_after = self._retry_after_seconds(exc)
        if retry_after is not None:
            delay = min(max(delay, retry_after), 120.0)
        return min(delay, 60.0)

    def _exhaustion_message(self, provider: str, max_attempts: int,
                            exc: BaseException, api_key: str) -> str:
        safe = self._redact_key(f"{type(exc).__name__}: {exc}", api_key)
        if self._is_rate_limit_error(exc):
            return (
                f"{provider} embedding failed after {max_attempts} attempts: "
                f"rate limit / quota exhausted ({safe[:200]}). "
                f"Reduce batch size or retry later."
            )
        return f"{provider} embedding request failed after {max_attempts} attempts: {safe[:300]}"

    async def _embed_by_api(self, texts: List[str], *,
                            task_type: Optional[str] = None) -> List[List[float]]:
        if not texts:
            return []
        if self._is_offline_embedding_mode():
            # Explicitly configured offline: deterministic zero vectors, no
            # network access even if an embedding API key is set in the environment.
            dim = max(1, int(self._runtime.psychagent_embedding_dimensions))
            self._logger.warning(
                "offline embedding mode: returning zero vectors (dim=%d); "
                "offline-deterministic, not semantic",
                dim,
            )
            return [[0.0] * dim for _ in texts]
        env_name = str(self._runtime.psychagent_embedding_api_key_env).strip()
        api_key = os.environ.get(env_name, "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                f"Embedding API key is required to backfill missing skill embeddings. "
                f"Please set environment variable '{env_name}'."
            )

        provider = str(self._runtime.psychagent_embedding_provider).strip().lower()
        if provider == "gemini":
            return await self._embed_by_gemini(api_key=api_key, texts=texts,
                                               task_type=task_type)
        return await self._embed_by_openai_compatible(api_key=api_key, texts=texts)

    @staticmethod
    def _redact_key(message: str, api_key: str) -> str:
        # Never leak the key in logs/errors even if an SDK echoes it back.
        if api_key and api_key in message:
            return message.replace(api_key, "<redacted>")
        return message

    async def _embed_by_gemini(self, api_key: str, texts: List[str], *,
                             task_type: Optional[str] = None) -> List[List[float]]:
        """Embed via the native Gemini SDK (google-genai).

        Model, output dimensionality, batch size, retry policy and timeout all
        come from the runtime config; nothing is hardcoded here.

        Task-type convention (documented choice): skill texts embedded at
        index/backfill time use ``RETRIEVAL_DOCUMENT``; the user query embedded
        at retrieval time uses ``RETRIEVAL_QUERY``. Both are passed explicitly
        by the callers; ``None`` leaves the SDK default in place.

        Note on normalization: this module scores with cosine similarity,
        which divides by both vector norms, so ranking is magnitude-invariant
        and no L2 normalization of stored vectors is required.
        """
        if genai is None:
            raise RuntimeError(
                "google-genai package is required for Gemini embeddings "
                "(psychagent_embedding_provider='gemini')"
            )
        model = str(self._runtime.psychagent_embedding_model).strip()
        if not model:
            raise RuntimeError("psychagent_embedding_model must be non-empty for Gemini embeddings")
        dimensions = max(1, int(self._runtime.psychagent_embedding_dimensions))
        batch_size = max(1, int(self._runtime.psychagent_embedding_batch_size))
        max_attempts = max(1, int(self._runtime.psychagent_embedding_max_retries))
        sleep_sec = float(self._runtime.psychagent_embedding_retry_sleep_sec)
        timeout_sec = max(1, int(self._runtime.psychagent_embedding_timeout_sec))

        from google.genai import types as genai_types

        embed_config = genai_types.EmbedContentConfig(
            output_dimensionality=dimensions,
            task_type=task_type,
        )
        # Timeout in ms; guards against hangs during client setup/TLS/handshake.
        http_options = genai_types.HttpOptions(timeout=timeout_sec * 1000)

        def _make_client() -> Any:
            return genai.Client(api_key=api_key, http_options=http_options)

        embeddings: List[List[float]] = []
        client = await asyncio.to_thread(_make_client)
        try:
            for start_idx in range(0, len(texts), batch_size):
                batch = texts[start_idx : start_idx + batch_size]
                for attempt in range(1, max_attempts + 1):
                    try:
                        resp = await asyncio.to_thread(
                            client.models.embed_content,
                            model=model,
                            contents=batch,
                            config=embed_config,
                        )
                        embeddings.extend(self._parse_gemini_embedding_response(resp, len(batch)))
                        break
                    except Exception as exc:
                        safe = self._redact_key(f"{type(exc).__name__}: {exc}", api_key)
                        if not self._is_retryable_embedding_error(exc):
                            raise RuntimeError(
                                f"Gemini embedding failed (not retryable): {safe[:300]}"
                            ) from exc
                        if attempt >= max_attempts:
                            raise RuntimeError(
                                self._exhaustion_message("Gemini", max_attempts, exc, api_key)
                            ) from exc
                        await asyncio.sleep(self._backoff_delay(attempt, sleep_sec, exc))
        finally:
            # The SDK always creates an internal httpx AsyncClient; close both
            # the sync and async clients to avoid 'aclose() never awaited'.
            # Shutdown is idempotent: each close is guarded and failures here
            # must not mask the original error.
            try:
                close = getattr(client, "close", None)
                if callable(close):
                    await asyncio.to_thread(close)
            finally:
                aclose = getattr(getattr(client, "aio", None), "aclose", None)
                if callable(aclose):
                    await aclose()
        return embeddings

    @staticmethod
    def _parse_gemini_embedding_response(resp: Any, expected_n: int) -> List[List[float]]:
        raw_embs = list(getattr(resp, "embeddings", None) or [])
        if len(raw_embs) != expected_n:
            raise ValueError(
                f"Gemini returned {len(raw_embs)} embeddings for {expected_n} input texts"
            )
        out: List[List[float]] = []
        for emb in raw_embs:
            vec = SkillManager._vector_to_list(getattr(emb, "values", None))
            if not vec:
                raise ValueError("Gemini returned an empty or malformed embedding vector")
            out.append(vec)
        return out

    async def _embed_by_openai_compatible(self, api_key: str, texts: List[str]) -> List[List[float]]:
        """Embed via an OpenAI-compatible /embeddings endpoint (e.g. SiliconFlow)."""
        if AsyncOpenAI is None:
            raise RuntimeError("openai package is required for embedding retrieval")

        timeout_sec = max(1, int(self._runtime.psychagent_embedding_timeout_sec))
        client = self._build_embedding_client(api_key=api_key, timeout_sec=timeout_sec)
        embeddings: List[List[float]] = []
        batch_size = max(1, int(self._runtime.psychagent_embedding_batch_size))
        max_attempts = max(1, int(self._runtime.psychagent_embedding_max_retries))
        sleep_sec = float(self._runtime.psychagent_embedding_retry_sleep_sec)

        for start_idx in range(0, len(texts), batch_size):
            batch = texts[start_idx : start_idx + batch_size]
            for attempt in range(1, max_attempts + 1):
                try:
                    resp = await client.embeddings.create(
                        input=batch,
                        model=self._runtime.psychagent_embedding_model,
                    )
                    batch_vecs = [self._vector_to_list(item.embedding) for item in resp.data]
                    if len(batch_vecs) != len(batch) or any(v is None for v in batch_vecs):
                        raise ValueError("embedding endpoint returned malformed vectors")
                    embeddings.extend([v for v in batch_vecs if v is not None])
                    break
                except Exception as exc:
                    safe = self._redact_key(f"{type(exc).__name__}: {exc}", api_key)
                    if not self._is_retryable_embedding_error(exc):
                        raise RuntimeError(
                            f"embedding failed (not retryable): {safe[:300]}"
                        ) from exc
                    if attempt >= max_attempts:
                        raise RuntimeError(
                            self._exhaustion_message("embedding", max_attempts, exc, api_key)
                        ) from exc
                    await asyncio.sleep(self._backoff_delay(attempt, sleep_sec, exc))

        return embeddings

    def _build_embedding_client(self, api_key: str, timeout_sec: int = 60) -> Any:
        if self._embedding_client is not None:
            return self._embedding_client

        kwargs: Dict[str, Any] = {}
        if not self._runtime.psychagent_embedding_verify_ssl:
            if httpx is None:
                raise RuntimeError("httpx is required when psychagent_embedding_verify_ssl=false")
            kwargs["http_client"] = httpx.AsyncClient(verify=False)

        self._embedding_client = AsyncOpenAI(
            api_key=api_key,
            base_url=self._runtime.psychagent_embedding_base_url,
            timeout=timeout_sec,
            **kwargs,
        )
        return self._embedding_client

    async def aclose(self) -> None:
        """Close cached embedding clients. Call when the SkillManager is retired."""
        client, self._embedding_client = self._embedding_client, None
        if client is not None:
            aclose = getattr(client, "close", None)
            if callable(aclose):
                res = aclose()
                if asyncio.iscoroutine(res):
                    await res


    def _load_prompts(self) -> None:
        select_dir = resolve_path(self._runtime.psychagent_skill_select_prompt_dir)
        rewrite_dir = resolve_path(self._runtime.psychagent_skill_rewrite_prompt_dir)

        self._select_system_prompt = (select_dir / "system.txt").read_text(encoding="utf-8")
        self._select_user_prompt = (select_dir / "user.txt").read_text(encoding="utf-8")
        self._rewrite_system_prompt = (rewrite_dir / "system.txt").read_text(encoding="utf-8")
        self._rewrite_user_prompt = (rewrite_dir / "user.txt").read_text(encoding="utf-8")

    def _normalize_sects(self, raw_sects: str | List[str]) -> List[str]:
        if isinstance(raw_sects, str):
            text = raw_sects.strip()
            if text.lower() == "all":
                return list(DEFAULT_SECTS)
            return [x.strip() for x in text.split(",") if x.strip()]

        sects = [str(x).strip() for x in raw_sects if str(x).strip()]
        if sects == ["all"]:
            return list(DEFAULT_SECTS)
        return sects or list(DEFAULT_SECTS)

    def _resolve_stage(self, stage: int | str) -> int:
        if isinstance(stage, int):
            return stage if stage in {1, 2, 3} else 1
        if isinstance(stage, str):
            stage = stage.strip()
            if stage.isdigit():
                parsed = int(stage)
                return parsed if parsed in {1, 2, 3} else 1
            return STAGE_MAP.get(stage, 1)
        return 1

    def _render_template(self, template_text: str, **kwargs: Any) -> str:
        if Template is None:
            return template_text
        return Template(template_text).render(**kwargs)

    @staticmethod
    def _load_json_dict(path: Path) -> Dict[str, Dict[str, Any]]:
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return {str(k): v for k, v in raw.items() if isinstance(v, dict)}

    def _embedding_store_key(self) -> str:
        """Filesystem-safe key identifying the configured embedding space.

        Regenerated vectors live in ``micro_skills.<key>.pt`` next to the
        originals, so earlier benchmark artifacts (e.g. bge-m3 vectors) are
        never overwritten and stay reproducible.
        """
        model = str(self._runtime.psychagent_embedding_model).strip() or "unknown-model"
        safe_model = re.sub(r"[^A-Za-z0-9_.-]", "_", model)
        dim = max(1, int(self._runtime.psychagent_embedding_dimensions))
        return f"{safe_model}.{dim}"

    def _provenance_matches(self, provenance: Any) -> bool:
        if not isinstance(provenance, dict):
            return False
        try:
            return (
                str(provenance.get("embedding_model")) == str(self._runtime.psychagent_embedding_model).strip()
                and int(provenance.get("embedding_dimensions"))
                == max(1, int(self._runtime.psychagent_embedding_dimensions))
            )
        except (TypeError, ValueError):
            return False

    def _build_provenance(self, source_hash: str, skill_count: int) -> Dict[str, Any]:
        import datetime as _dt

        return {
            "embedding_provider": str(self._runtime.psychagent_embedding_provider),
            "embedding_model": str(self._runtime.psychagent_embedding_model),
            "embedding_dimensions": int(self._runtime.psychagent_embedding_dimensions),
            "index_task_type": "RETRIEVAL_DOCUMENT",
            "query_task_type": "RETRIEVAL_QUERY",
            # Vectors are stored raw (not L2-normalized): this module scores
            # with cosine similarity, which normalizes explicitly, so ranking
            # is magnitude-invariant.
            "l2_normalized": False,
            "created_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "source_file_sha256": source_hash,
            "skill_count": int(skill_count),
            "vector_fields": ["embedding_to_merge", "embedding_to_retrive"],
        }

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def _load_micro_skills(self, stage_dir: Path) -> Dict[str, Dict[str, Any]]:
        base_pt_path = stage_dir / "micro_skills.pt"
        keyed_pt_path = stage_dir / f"micro_skills.{self._embedding_store_key()}.pt"
        json_path = stage_dir / "micro_skills.json"

        raw: Dict[str, Any] = {}
        # 1. Prefer the provenance-keyed store for the configured space.
        if keyed_pt_path.exists() and torch is not None:
            loaded = torch.load(str(keyed_pt_path), weights_only=False)
            if isinstance(loaded, dict):
                provenance = loaded.pop("_provenance", None)
                if self._provenance_matches(provenance):
                    raw = loaded
                else:
                    self._logger.warning(
                        "Ignoring %s: provenance %s does not match configured %s/%s",
                        keyed_pt_path.name, provenance,
                        self._runtime.psychagent_embedding_model,
                        self._runtime.psychagent_embedding_dimensions,
                    )
        # 2. Fall back to the original artifacts (dimension guard downstream
        #    re-embeds on mismatch instead of mixing vector spaces).
        if not raw:
            if base_pt_path.exists() and torch is not None:
                loaded = torch.load(str(base_pt_path), weights_only=False)
                if isinstance(loaded, dict):
                    loaded.pop("_provenance", None)
                    raw = loaded
            elif json_path.exists():
                loaded = json.loads(json_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    raw = loaded

        cleaned: Dict[str, Dict[str, Any]] = {}
        for key, value in raw.items():
            if isinstance(value, dict):
                value = dict(value)
                if "skill_id" not in value:
                    value["skill_id"] = str(key)
                cleaned[str(key)] = value
        return cleaned

    @staticmethod
    def _extract_json_object(text: str) -> Dict[str, Any]:
        if not text:
            return {}

        inner = extract_tag_content(text, "response") or text
        inner = inner.strip()
        if inner.startswith("```"):
            inner = re.sub(r"^```(?:json)?", "", inner).strip()
            inner = re.sub(r"```$", "", inner).strip()

        try:
            parsed = json.loads(inner)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        match = re.search(r"\{.*\}", inner, re.S)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        return {}

    @staticmethod
    def _vector_to_list(value: Any) -> Optional[List[float]]:
        if value is None:
            return None

        if isinstance(value, list):
            try:
                return [float(x) for x in value]
            except Exception:
                return None

        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            try:
                listed = tolist()
                if isinstance(listed, list):
                    return [float(x) for x in listed]
            except Exception:
                return None

        return None

    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return -1.0
        num = sum(a * b for a, b in zip(v1, v2))
        den1 = math.sqrt(sum(a * a for a in v1))
        den2 = math.sqrt(sum(b * b for b in v2))
        if den1 == 0 or den2 == 0:
            return -1.0
        return num / (den1 * den2)
