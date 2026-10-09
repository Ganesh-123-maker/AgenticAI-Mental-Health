"""Jinja2-based prompt rendering utilities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .schemas import ClientCase, PublicMemory

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
except ImportError:  # pragma: no cover - fallback path for minimal environments
    Environment = None  # type: ignore[assignment]
    FileSystemLoader = None  # type: ignore[assignment]
    StrictUndefined = None  # type: ignore[assignment]


@dataclass
class PromptManager:
    """Loads and renders public and client prompts."""

    prompt_root: Path
    _env: Optional[Any] = None

    def __post_init__(self) -> None:
        if Environment is not None:
            self._env = Environment(
                loader=FileSystemLoader(str(self.prompt_root)),
                autoescape=False,
                undefined=StrictUndefined,
                trim_blocks=True,
                lstrip_blocks=True,
            )

    def render_template(self, template_relpath: str, **kwargs: Any) -> str:
        if self._env is not None:
            template = self._env.get_template(template_relpath)
            return template.render(**kwargs).strip()

        # Fallback: simple replacement for {{ key }} expressions.
        path = self.prompt_root / template_relpath
        text = path.read_text(encoding="utf-8")
        return _simple_render(text, kwargs).strip()

    def render_counselor_system(
        self,
        *,
        modality: str,
        session_index: int,
        output_language: str,
        end_token: str,
        public_memory: PublicMemory,
        therapy_name: Optional[str] = None,
    ) -> str:
        known_static_traits_text = (
            json.dumps(public_memory.known_static_traits, ensure_ascii=False, indent=2)
            if public_memory.known_static_traits
            else "(No confirmed background information)"
        )
        session_recaps_text = (
            json.dumps(public_memory.session_recaps, ensure_ascii=False, indent=2)
            if public_memory.session_recaps
            else "(No prior session records)"
        )
        last_homework_text = (
            json.dumps(public_memory.last_homework, ensure_ascii=False, indent=2)
            if public_memory.last_homework
            else "(None)"
        )

        return self.render_template(
            "public/counselor_system.jinja2",
            therapy_name=therapy_name or _normalize_therapy_name(modality),
            modality=modality,
            session_index=session_index,
            output_language=output_language,
            end_token=end_token,
            known_static_traits_text=known_static_traits_text,
            session_recaps_text=session_recaps_text,
            last_homework_text=last_homework_text,
        )

    def render_session_opening(self, *, modality: str, session_index: int, end_token: str = "</end>") -> str:
        return self.render_template(
            "public/session_opening.jinja2",
            modality=modality,
            session_index=session_index,
            end_token=end_token,
        )

    def render_public_recap(self, *, public_memory: PublicMemory) -> str:
        recap_items = [
            {
                "session_index": item.get("session_index", idx + 1),
                "summary": item.get("summary", ""),
                "homework": item.get("homework", []),
                "static_traits": item.get("static_traits", {}),
            }
            for idx, item in enumerate(public_memory.session_recaps)
        ]
        return self.render_template(
            "public/public_recap.jinja2",
            known_static_traits_json=json.dumps(public_memory.known_static_traits, ensure_ascii=False, indent=2),
            recaps_json=json.dumps(recap_items, ensure_ascii=False, indent=2),
            last_homework_json=json.dumps(public_memory.last_homework, ensure_ascii=False),
        )

    def render_client_dialogue(
        self,
        *,
        case: ClientCase,
        session_index: int,
        prior_transcript: list[dict[str, Any]],
        output_language: str,
        public_memory: Optional[PublicMemory] = None,
        client_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        normalized_client_state = client_state or {}
        intake_profile = dict(case.intake_profile)
        if "static_traits" not in intake_profile or not isinstance(intake_profile.get("static_traits"), dict):
            intake_profile["static_traits"] = dict(case.basic_info)
        if "growth_experiences" not in intake_profile or not isinstance(intake_profile.get("growth_experiences"), list):
            intake_profile["growth_experiences"] = []

        last_counselor_message = ""
        for msg in reversed(prior_transcript):
            if msg.get("role") == "assistant":
                last_counselor_message = str(msg.get("content", "")).strip()
                break

        session_recaps = (
            list(public_memory.session_recaps)
            if public_memory is not None
            else list(normalized_client_state.get("session_recaps", []))
        )
        last_homework = (
            list(public_memory.last_homework)
            if public_memory is not None
            else list(normalized_client_state.get("homework_history", []))
        )
        modality_profile_text = json.dumps(case.theory_info, ensure_ascii=False, indent=2) if case.theory_info else "Unknown"

        if self._env is None:
            return self._render_client_dialogue_fallback(
                intake_profile=intake_profile,
                session_index=session_index,
                session_recaps=session_recaps,
                last_homework=last_homework,
                modality_profile_text=modality_profile_text,
                last_counselor_message=last_counselor_message,
            )

        return self.render_template(
            "client/dialogue.jinja2",
            modality=case.modality,
            session_index=session_index,
            intake_profile=intake_profile,
            session_recaps=session_recaps,
            last_homework=last_homework,
            modality_profile_text=modality_profile_text,
            last_counselor_message=last_counselor_message,
            client_state=normalized_client_state,
            prior_transcript=prior_transcript,
            output_language=output_language,
        )

    def _render_client_dialogue_fallback(
        self,
        *,
        intake_profile: Dict[str, Any],
        session_index: int,
        session_recaps: list[dict[str, Any]],
        last_homework: list[str],
        modality_profile_text: str,
        last_counselor_message: str,
    ) -> str:
        info = intake_profile.get("static_traits", {})
        if not isinstance(info, dict):
            info = {}

        def _v(obj: Dict[str, Any], key: str, default: str = "Unknown") -> str:
            value = obj.get(key)
            if value is None:
                return default
            text = str(value).strip()
            return text if text else default

        growth = intake_profile.get("growth_experiences")
        if isinstance(growth, list) and growth:
            growth_lines = "\n".join(f"- {item}" for item in growth)
        else:
            growth_lines = "- Unknown"

        if session_recaps:
            history_blocks = []
            for idx, rec in enumerate(session_recaps, start=1):
                summary = str(rec.get("summary", "None") or "None")
                block_lines = [f"[Session {idx}]", f"- Summary: {summary}"]
                history_blocks.append("\n".join(block_lines))
            history_text = "\n".join(history_blocks)
        else:
            history_text = "(No prior session records)"

        homework_text = "\n".join(f"- {x}" for x in last_homework) if last_homework else "(None)"
        last_counselor_text = last_counselor_message if last_counselor_message else "(None)"

        return (
            f"You are not an AI. You are a real client named {_v(info, 'name', 'Client')}.\n"
            "You are currently participating in an online psychological counseling session.\n"
            "You must always speak in the first person ('I'), outputting only what you would say directly to your counselor.\n\n"
            f"This is Session {session_index}.\n\n"
            "【Your Background】\n"
            f"- Name: {_v(info, 'name')}\n"
            f"- Age: {_v(info, 'age')}\n"
            f"- Gender: {_v(info, 'gender')}\n"
            f"- Occupation: {_v(info, 'occupation')}\n"
            f"- Educational Background: {_v(info, 'educational_background')}\n"
            f"- Marital Status: {_v(info, 'marital_status')}\n"
            f"- Family Status: {_v(info, 'family_status')}\n"
            f"- Social Status: {_v(info, 'social_status')}\n"
            f"- Medical History: {_v(info, 'medical_history')}\n"
            f"- Communication Style: {_v(info, 'language_features')}\n\n"
            "【Current Concerns & Counseling Goals】\n"
            f"- Chief Complaint: {_v(intake_profile, 'main_problem')}\n"
            f"- Topic: {_v(intake_profile, 'topic')}\n"
            f"- Core Demands: {_v(intake_profile, 'core_demands')}\n\n"
            "【Developmental History】\n"
            f"{growth_lines}\n\n"
            "【Supplementary Clinical Profile】\n"
            f"{modality_profile_text}\n\n"
            "【Previous Session Overview】\n"
            f"{history_text}\n\n"
            "【Previous Homework】\n"
            f"{homework_text}\n\n"
            "【Counselor's Latest Utterance】\n"
            f"{last_counselor_text}\n\n"
            "【Consistency Guidelines】\n"
            "1. Your response must remain consistent with your persona, past sessions, and current concerns.\n"
            "2. If an issue was already discussed previously, follow up naturally rather than introducing yourself again.\n"
            "3. If certain details are unknown, say 'I'm not sure' or 'I haven't thought about that', without inventing unrelated details.\n"
            "4. Do not sound clinical or like a textbook.\n\n"
            "【Communication Guidelines】\n"
            "1. Speak naturally and conversationally.\n"
            "2. Keep responses concise (typically 2-4 sentences).\n"
            "3. Do not use clinical jargon, systematize yourself, or write like a report.\n"
            "4. Disclose information gradually rather than revealing all deep issues at once.\n"
            "5. You may answer directly or share a brief relevant personal experience.\n\n"
            "【Behavioral & Interactive Style】\n"
            "1. You are generally willing to engage, but are not a perfectly compliant client.\n"
            "2. When sensitive topics arise, you may hesitate, minimize, give vague answers, or mildly deflect.\n"
            "3. Your emotional trajectory is non-linear; feelings may fluctuate naturally.\n"
            "4. React genuinely to counselor statements—showing feeling understood, confused, skeptical, or wanting to continue.\n"
            "5. You may occasionally go slightly off-topic if emotionally relevant.\n\n"
            "【Strict Constraints】\n"
            "1. Output ONLY the words you say aloud as the client.\n"
            "2. Do NOT output stage directions, facial expressions, bracketed notes, or psychological thought tags.\n"
            "3. Do NOT output meta-statements like 'As a client' or 'According to my persona'.\n"
            "4. Do NOT speak on behalf of the counselor.\n"
            "5. Do NOT output JSON, XML, bullet points, or markdown formatting.\n\n"
            "Now, respond naturally to the counselor's latest statement as the client."
        )


def _simple_render(template: str, values: Dict[str, Any]) -> str:
    pattern = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

    def _repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"missing template variable: {key}")
        return str(values[key])

    return pattern.sub(_repl, template)


def _normalize_therapy_name(modality: str) -> str:
    key = modality.strip().lower()
    mapping = {
        "cbt": "Cognitive Behavioral Therapy (CBT)",
        "act": "Acceptance and Commitment Therapy (ACT)",
        "dbt": "Dialectical Behavior Therapy (DBT)",
        "psychodynamic": "Psychodynamic Therapy",
        "bt": "Behavioral Therapy (BT)",
        "het": "Humanistic-Existential Therapy (HET)",
        "pdt": "Psychodynamic Therapy (PDT)",
        "pmt": "Postmodern Therapy (PMT)",
    }
    return mapping.get(key, modality)
