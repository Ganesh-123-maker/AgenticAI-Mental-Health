"""Regenerate skill embeddings into provenance-keyed stores (Gemini migration).

Reads the ORIGINAL skill artifacts (assets/skills/sect/*/stage*/micro_skills.pt
- never modified) and writes regenerated vectors to SEPARATE files:

    micro_skills.<model>.<dims>.pt      e.g. micro_skills.gemini-embedding-001.768.pt

Rate limits (free tier, gemini-embedding-001): ~100 requests/min, ~30,000
tokens/min, ~1,000 requests/day. This script paces itself under all three
(--rpm, --tpm) and honors server retry delays. SDK-internal retries are
disabled by the SkillManager so one logical attempt is one HTTP request.

Resumability: each file is checkpointed at BATCH granularity into
    micro_skills.<model>.<dims>.pt.partial
(an atomic temp-then-rename write per batch). Interrupting and re-running
reuses completed batches. The final store is assembled only when every batch
is present, validated (count, dimensions, finite values, skill-id ordering),
then atomically renamed; the partial file is deleted afterwards.

A lock file prevents two concurrent runs from sharing the quota.

Usage (PowerShell):
    # dry run: demand estimate + projected duration, no API calls, no writes
    python scripts/migrate_skill_embeddings.py --runtime configs/runtime/multi_agent_gemini.yaml --dry-run
    # live run (default 30 RPM, 25k TPM):
    python scripts/migrate_skill_embeddings.py --runtime configs/runtime/multi_agent_gemini.yaml
    # resume is automatic; limit scope:
    python scripts/migrate_skill_embeddings.py --runtime <yaml> --sects cbt

The API key is read from the environment variable named in the runtime config
and never printed. Daily-quota 429s stop immediately with resume instructions.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import math
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    import torch
except ImportError:
    torch = None  # type: ignore[assignment]

from sample.io.config_loader import load_runtime_config
from sample.skill_manager import SkillManager
from shared.file_utils import resolve_path

VECTOR_FIELDS = ("embedding_to_merge", "embedding_to_retrive")


class _NullBackend:
    """Minimal backend: live embedding path only needs the runtime config."""

    is_offline = False

    async def chat_text(self, messages, **kwargs):
        raise RuntimeError("migration script never calls the chat backend")


class RatePacer:
    """Enforces minimum intervals for requests/min and estimated tokens/min.

    Adaptive: after a per-minute 429 the interval widens multiplicatively for
    the rest of the run; successful requests relax it slowly toward the base.
    """

    def __init__(self, rpm: float, tpm: float | None, est_tokens_per_request: float):
        interval_rpm = 60.0 / max(1.0, float(rpm))
        interval = interval_rpm
        self.tpm_active = False
        if tpm and est_tokens_per_request > 0:
            interval_tpm = 60.0 * est_tokens_per_request / float(tpm)
            if interval_tpm > interval:
                interval = interval_tpm
                self.tpm_active = True
        self.base_interval = interval
        self.interval = interval
        self.adaptations = 0
        self._last: float = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = asyncio.get_running_loop().time()
            delay = self._last + self.interval - now
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = asyncio.get_running_loop().time()
            # Slow relax toward the base interval after each successful wait.
            if self.interval > self.base_interval:
                self.interval = max(self.base_interval, self.interval * 0.95)

    def adapt_on_429(self) -> None:
        """Widen the interval after a per-minute 429 (capped at 60s)."""
        new_interval = min(self.interval * 1.5, 60.0)
        if new_interval > self.interval:
            self.interval = new_interval
            self.adaptations += 1


def _redact(msg: str, env_name: str) -> str:
    key = os.environ.get(env_name, "")
    return msg.replace(key, "<redacted>") if key else msg


def _iter_base_files(base_dir: Path, sects: list[str]) -> list[Path]:
    files = []
    for sect in sects:
        for stage_dir in sorted((base_dir / sect).glob("stage*")):
            pt = stage_dir / "micro_skills.pt"
            if pt.exists():
                files.append(pt)
    return files


def _load_base_skills(pt_path: Path) -> dict:
    loaded = torch.load(str(pt_path), weights_only=False)
    if not isinstance(loaded, dict):
        raise ValueError(f"{pt_path} did not contain a dict")
    loaded.pop("_provenance", None)
    return {str(k): dict(v) for k, v in loaded.items() if isinstance(v, dict)}


def _skill_texts(skill: dict) -> tuple[str, str]:
    merge = json.dumps(
        {k: skill.get(k, "") for k in (
            "skill_id", "skill_name", "skill_description",
            "trigger", "when_to_use", "parent_ids")},
        ensure_ascii=False,
    )
    retrieve = f"Trigger:{skill.get('trigger', '')}\nWhen_to_Use:{skill.get('when_to_use', '')}"
    return merge, retrieve


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or
            0x20000 <= o <= 0x2A6DF or 0xF900 <= o <= 0xFAFF or
            0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF)


def _est_tokens(text: str, multiplier: float = 1.0) -> float:
    """Conservative, CJK-aware token ESTIMATE (not a count).

    About 1 token per CJK character, about 0.25 per other character.
    The multiplier lets operators add headroom; the result is still an
    estimate, never treated as an exact token count.
    """
    return sum(1.0 if _is_cjk(ch) else 0.25 for ch in text) * multiplier


def _est_tokens_optimistic(text: str) -> float:
    """Legacy len/4 estimate, kept for comparison in dry-run output."""
    return len(text) / 4.0


def _keyed_name(manager: SkillManager) -> str:
    return f"micro_skills.{manager._embedding_store_key()}.pt"


def _file_batch_count(n_skills: int, batch_size: int) -> int:
    """Exact number of API requests for one file.

    Merge and retrieve texts are batched SEPARATELY (they are different
    texts), so a file with N skills needs 2 * ceil(N / batch_size) requests.
    This is the single source of truth used for quota checks, duration
    estimates, TPM pacing, and shard checkpointing.
    """
    batch_size = max(1, int(batch_size))
    per_field = (max(0, int(n_skills)) + batch_size - 1) // batch_size
    return 2 * per_field


class DailyQuotaExhausted(RuntimeError):
    """Raised when the provider's daily quota is exhausted: abort the run."""


def _lock_token() -> str:
    """Unique owner token: pid + random suffix (guards against PID reuse)."""
    import uuid
    return f"{os.getpid()}-{uuid.uuid4().hex[:8]}"


def _lock_owner_alive(info: dict) -> bool:
    """True if the lock records a currently-running process.

    os.kill(pid, 0) is an existence check on both POSIX and Windows
    (no signal is delivered). A live owner is NEVER displaced, no matter
    how old the lock is.
    """
    pid = info.get("pid")
    if isinstance(pid, int) and pid > 0:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False
    return False


def _acquire_lock(lock_path: Path, race_timeout_sec: float = 30.0) -> str:
    """Create the lock file atomically, or take over / refuse clearly.

    - Creation uses O_CREAT|O_EXCL: exactly one racing process can win.
    - A lock whose owner process is still alive is never displaced.
    - A stale lock (dead PID or malformed) is taken over via
      verify-then-replace plus a post-replace ownership confirmation,
      so two racing processes cannot both believe they own it.
    Returns the owner token; _release_lock only removes the lock if the
    token still matches.
    """
    token = _lock_token()
    payload = json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                          "pid": os.getpid(), "token": token})
    deadline = time.time() + race_timeout_sec
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, payload.encode("utf-8"))
            finally:
                os.close(fd)
            return token
        except FileExistsError:
            pass

        try:
            info = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            info = {}
        if _lock_owner_alive(info):
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                age = 0.0
            raise RuntimeError(
                f"lock file present ({lock_path.name}): another migration is "
                f"active (pid {info.get('pid')}, started "
                f"{info.get('at', 'unknown')}, age {age:.0f}s). Delete it "
                f"only if no migration is running.")

        # Stale lock: compare-and-swap takeover.
        try:
            before = lock_path.read_bytes()
        except OSError:
            continue  # vanished between checks; retry the atomic create
        tmp = lock_path.with_name(f"{lock_path.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text(payload, encoding="utf-8")
            try:
                unchanged = (lock_path.read_bytes() == before)
            except OSError:
                unchanged = False
            if not unchanged:
                continue  # someone else acted; re-evaluate from the top
            os.replace(str(tmp), str(lock_path))
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
        # Confirm we still own it after the replace (closes the race window).
        time.sleep(0.05)
        try:
            cur = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            cur = {}
        if cur.get("token") == token:
            logging.getLogger(__name__).warning(
                "took over stale lock %s (previous owner pid %s)",
                lock_path.name, info.get("pid"))
            return token
        if time.time() > deadline:
            raise RuntimeError(
                f"could not acquire lock {lock_path.name}: lost a takeover "
                f"race. Another process may be starting; retry the command.")
        # Lost the race; loop and re-evaluate (likely a live lock now).


def _release_lock(lock_path: Path, token: str | None = None) -> None:
    """Remove the lock only if we still own it (token match).

    If another process took over the lock after us (stale takeover), we
    must not delete their lock.
    """
    try:
        if token is not None and lock_path.exists():
            try:
                info = json.loads(lock_path.read_text(encoding="utf-8"))
            except Exception:
                info = {}
            if info.get("token") != token:
                logging.getLogger(__name__).warning(
                    "not removing lock %s: owned by another process",
                    lock_path.name)
                return
        lock_path.unlink()
    except OSError:
        pass


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class ShardCheckpoint:
    """Batch-granularity checkpoint for one skill file.

    Partial state lives in <keyed>.partial (atomic temp-then-rename per batch):
      {"source_hash": ..., "provenance": {...}, "total_batches": N,
       "batches": {"0": [[...]], ...}, "skill_ids": [...]}
    """

    def __init__(self, keyed_path: Path, source_hash: str, provenance: dict,
                 skill_ids: list[str], total_batches: int):
        self.keyed_path = keyed_path
        self.partial_path = keyed_path.with_name(keyed_path.name + ".partial")
        self.source_hash = source_hash
        self.provenance = provenance
        self.skill_ids = skill_ids
        self.total_batches = total_batches
        self.done: dict[int, list] = {}

    def load(self) -> int:
        """Load valid partial state. Returns number of reusable batches."""
        if not self.partial_path.exists():
            return 0
        try:
            state = torch.load(str(self.partial_path), weights_only=False)
        except Exception:
            return 0
        if not isinstance(state, dict):
            return 0
        if state.get("source_hash") != self.source_hash:
            return 0
        prov = state.get("provenance") or {}
        if (str(prov.get("embedding_model")) != str(self.provenance.get("embedding_model"))
                or int(prov.get("embedding_dimensions", -1))
                != int(self.provenance.get("embedding_dimensions", -2))):
            return 0
        if state.get("skill_ids") != self.skill_ids:
            return 0
        batches = state.get("batches") or {}
        self.done = {int(k): v for k, v in batches.items()
                     if isinstance(v, list) and len(v) > 0}
        return len(self.done)

    def save_batch(self, idx: int, vectors: list) -> None:
        self.done[idx] = [list(map(float, v)) for v in vectors]
        state = {
            "source_hash": self.source_hash,
            "provenance": self.provenance,
            "skill_ids": self.skill_ids,
            "total_batches": self.total_batches,
            "batches": {str(k): v for k, v in self.done.items()},
        }
        tmp = self.partial_path.with_suffix(".partial.tmp")
        torch.save(state, str(tmp))
        os.replace(str(tmp), str(self.partial_path))

    def is_complete(self) -> bool:
        return len(self.done) >= self.total_batches and all(
            i in self.done for i in range(self.total_batches))

    def ordered_vectors(self) -> list:
        out: list = []
        for i in range(self.total_batches):
            out.extend(self.done[i])
        return out

    def discard(self) -> None:
        try:
            self.partial_path.unlink()
        except OSError:
            pass


def _validate_vectors(vectors: list, expected_count: int, dim: int) -> str | None:
    if len(vectors) != expected_count:
        return f"count {len(vectors)} != {expected_count}"
    for v in vectors:
        if not isinstance(v, list) or len(v) != dim:
            return f"bad dimension (expected {dim})"
        if not all(isinstance(x, float) and math.isfinite(x) for x in v):
            return "non-finite value"
    return None


async def _migrate_one(manager: SkillManager, pt_path: Path, dry_run: bool,
                       pacer: RatePacer, env_name: str) -> dict:
    keyed_path = pt_path.parent / _keyed_name(manager)
    lock_path = keyed_path.with_name(keyed_path.name + ".lock")
    stats: dict = {"source": str(pt_path), "target": keyed_path.name}

    if torch is None:
        return {**stats, "status": "FAILED: torch is required"}

    skills = _load_base_skills(pt_path)
    skill_ids = sorted(skills.keys())
    stats["skills"] = len(skill_ids)
    source_hash = _sha256_file(pt_path)
    provenance = manager._build_provenance(source_hash, len(skill_ids))

    # Build texts (merge + retrieve are different texts; measured unique).
    merge_texts, retrieve_texts = [], []
    for sid in skill_ids:
        m, r = _skill_texts(skills[sid])
        merge_texts.append(m)
        retrieve_texts.append(r)
    batch_size = max(1, int(manager._runtime.psychagent_embedding_batch_size))

    def _batches(texts: list[str]) -> list[list[str]]:
        return [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]

    merge_batches = _batches(merge_texts)
    retrieve_batches = _batches(retrieve_texts)
    total_batches = len(merge_batches) + len(retrieve_batches)
    # Self-check: the executed batching must match the demand estimate.
    expected = _file_batch_count(len(skill_ids), batch_size)
    if total_batches != expected:
        raise RuntimeError(
            f"batching mismatch: built {total_batches} batches but "
            f"_file_batch_count predicts {expected}")
    est_tokens = sum(_est_tokens(t) for t in merge_texts + retrieve_texts)
    stats["batches"] = total_batches
    stats["est_tokens"] = round(est_tokens)

    if dry_run:
        return {**stats, "status": "dry-run (no API calls, no writes)"}

    # Resumability: completed keyed store with matching provenance.
    if keyed_path.exists():
        try:
            existing = torch.load(str(keyed_path), weights_only=False)
            if isinstance(existing, dict) and manager._provenance_matches(
                    existing.get("_provenance")):
                # Validate only the expected skill ids: the keyed store also
                # carries a "_provenance" entry, which must not be treated as
                # a skill (v6 fix: the old existing.values() comprehension hit
                # the provenance dict, raised KeyError, and the surrounding
                # `except Exception: pass` silently disabled this skip path,
                # so completed files were re-embedded on every run).
                problem = _validate_vectors(
                    [existing[sid]["embedding_to_merge"] for sid in skill_ids
                     if isinstance(existing.get(sid), dict)],
                    len(skill_ids), int(manager._runtime.psychagent_embedding_dimensions))
                if problem is None:
                    return {**stats, "status": "skipped (valid store present)"}
        except Exception:
            pass

    # Lock against concurrent runs sharing the quota. Released in the
    # finally block below, which also covers exceptions, KeyboardInterrupt
    # and asyncio.CancelledError. The owner token prevents us from deleting
    # another process's lock after a stale takeover.
    lock_token = _acquire_lock(lock_path)

    checkpoint = ShardCheckpoint(keyed_path, source_hash, provenance,
                                 skill_ids, total_batches)
    reused = checkpoint.load()
    stats["reused_batches"] = reused
    if reused:
        logging.getLogger(__name__).info(
            "resuming %s: %d/%d batches already done", keyed_path.name, reused, total_batches)

    dim = max(1, int(manager._runtime.psychagent_embedding_dimensions))
    try:
        batch_idx = 0
        # Order of batch indices: merge batches 0..M-1, retrieve batches M..M+R-1
        for batch in merge_batches:
            if batch_idx not in checkpoint.done:
                await pacer.wait()
                vecs = await manager._embed_by_api(
                    batch, task_type="RETRIEVAL_DOCUMENT",
                    on_rate_limit=pacer.adapt_on_429)
                problem = _validate_vectors(vecs, len(batch), dim)
                if problem:
                    raise RuntimeError(f"merge batch {batch_idx}: {problem}")
                checkpoint.save_batch(batch_idx, vecs)
            batch_idx += 1
        for batch in retrieve_batches:
            if batch_idx not in checkpoint.done:
                await pacer.wait()
                vecs = await manager._embed_by_api(
                    batch, task_type="RETRIEVAL_DOCUMENT",
                    on_rate_limit=pacer.adapt_on_429)
                problem = _validate_vectors(vecs, len(batch), dim)
                if problem:
                    raise RuntimeError(f"retrieve batch {batch_idx}: {problem}")
                checkpoint.save_batch(batch_idx, vecs)
            batch_idx += 1

        ordered = checkpoint.ordered_vectors()
        n_merge = len(merge_texts)
        merge_vecs, retrieve_vecs = ordered[:n_merge], ordered[n_merge:]
        problem = _validate_vectors(merge_vecs + retrieve_vecs, len(skill_ids) * 2, dim)
        if problem:
            return {**stats, "status": f"FAILED: assembled store invalid: {problem}"}
        for sid, mv, rv in zip(skill_ids, merge_vecs, retrieve_vecs):
            skills[sid]["embedding_to_merge"] = mv
            skills[sid]["embedding_to_retrive"] = rv

        payload = {sid: skills[sid] for sid in skill_ids}
        payload["_provenance"] = provenance
        tmp = keyed_path.with_suffix(".pt.tmp")
        torch.save(payload, str(tmp))
        os.replace(str(tmp), str(keyed_path))
        checkpoint.discard()
        return {**stats, "status": "regenerated", "dim": dim,
                "reused_batches": reused}
    except Exception as exc:  # noqa: BLE001 - per-file failure, keep going
        msg = _redact(f"{type(exc).__name__}: {exc}", env_name)
        if "daily quota" in msg.lower():
            # Abort the whole run: retrying sooner is pointless.
            raise DailyQuotaExhausted(msg[:220])
        return {**stats, "status": f"FAILED: {msg[:220]}"}
    finally:
        # Always release the lock: success, failure, KeyboardInterrupt,
        # asyncio.CancelledError. Stale locks from killed processes are
        # detected on acquire.
        _release_lock(lock_path, lock_token)


def _compute_demand(base_files: list[Path], batch_size: int,
                    token_multiplier: float) -> tuple[int, float, float, int]:
    """Offline demand estimate (no API calls): measure real texts.

    Returns (total_texts, optimistic_tokens, conservative_tokens,
    total_requests). The request count uses _file_batch_count per file, so
    it exactly matches the batching _migrate_one will execute.
    """
    total_texts = 0
    opt_tokens = 0.0
    cons_tokens = 0.0
    total_batches = 0
    if torch is not None:
        for pt in base_files:
            try:
                skills = _load_base_skills(pt)
            except Exception:
                continue
            total_batches += _file_batch_count(len(skills), batch_size)
            for skill in skills.values():
                m, r = _skill_texts(skill)
                total_texts += 2
                opt_tokens += _est_tokens_optimistic(m) + _est_tokens_optimistic(r)
                cons_tokens += (_est_tokens(m, token_multiplier)
                                + _est_tokens(r, token_multiplier))
    return total_texts, opt_tokens, cons_tokens, total_batches


async def _run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_runtime_config(args.runtime)
    env_name = str(cfg.psychagent_embedding_api_key_env).strip()
    if not args.dry_run and not os.environ.get(env_name, "").strip():
        print(f"FAIL: environment variable '{env_name}' is not set (value never printed)")
        return 2

    base_dir = resolve_path(cfg.psychagent_skill_base_dir)
    sects = [s.strip() for s in args.sects.split(",") if s.strip()] \
        if args.sects else ["bt", "cbt", "het", "pdt", "pmt"]
    base_files = _iter_base_files(base_dir, sects)
    if not base_files:
        print(f"FAIL: no micro_skills.pt found under {base_dir}")
        return 1

    manager = SkillManager(_NullBackend(), cfg)
    batch_size = max(1, int(cfg.psychagent_embedding_batch_size))

    total_texts, opt_tokens, cons_tokens, total_batches = _compute_demand(
        base_files, batch_size, args.token_multiplier)
    cons_tpr = (cons_tokens / total_batches) if total_batches else 0.0
    pacer = RatePacer(args.rpm, args.tpm, cons_tpr)

    print(f"found {len(base_files)} base files | provider={cfg.psychagent_embedding_provider} "
          f"model={cfg.psychagent_embedding_model} dim={cfg.psychagent_embedding_dimensions}")
    print(f"demand (measured offline): {total_texts} texts, "
          f"~{opt_tokens:.0f} est tokens (optimistic len/4) / "
          f"~{cons_tokens:.0f} est tokens (conservative CJK-aware x{args.token_multiplier}), "
          f"{total_batches} requests @ batch {batch_size}")
    print(f"pacing: {args.rpm:.1f} RPM" +
          (f", {args.tpm:.0f} TPM (active)" if pacer.tpm_active else f" (TPM cap {args.tpm:.0f} not binding)") +
          f" -> interval {pacer.interval:.2f}s/request")
    if total_batches:
        cons_minutes = total_batches * pacer.interval / 60.0
        # Optimistic duration under RPM pacing alone (no TPM binding).
        opt_interval = 60.0 / max(1.0, float(args.rpm))
        opt_minutes = total_batches * opt_interval / 60.0
        print(f"projected duration: ~{opt_minutes:.0f} min (optimistic) / "
              f"~{cons_minutes:.0f} min (conservative) for {total_batches} requests "
              f"({total_batches/1000*100:.0f}% of 1000/day free-tier requests)")
    print(f"target suffix .{manager._embedding_store_key()}.pt | "
          "originals are never modified; output goes to separate keyed files")
    if args.rpd and total_batches > args.rpd:
        print(f"FAIL: {total_batches} requests exceed --rpd {args.rpd}; refusing to start")
        return 2

    if args.dry_run:
        print("dry-run: no API calls, no writes")
        return 0

    resume_cmd = ("python scripts/migrate_skill_embeddings.py "
                    f"--runtime {args.runtime}"
                    + (f" --sects {args.sects}" if args.sects else ""))
    results = []
    aborted = False
    for pt in base_files:
        if aborted:
            results.append({"source": str(pt),
                            "status": "INCOMPLETE: run aborted (daily quota exhausted)"})
            continue
        try:
            results.append(await _migrate_one(manager, pt, args.dry_run, pacer, env_name))
        except DailyQuotaExhausted as dq:
            aborted = True
            results.append({"source": str(pt),
                            "status": f"INCOMPLETE: {dq}. Quota resets at midnight Pacific."})
        except Exception as exc:  # noqa: BLE001
            msg = _redact(f"{type(exc).__name__}: {exc}", env_name)
            results.append({"source": str(pt), "status": f"FAILED: {msg[:220]}"})
    if aborted:
        for r in results:
            print(f"  [{r['status']}] {r['source']}")
        print(f"ABORTED: daily quota exhausted. {sum(1 for r in results if r['status'].startswith('INCOMPLETE'))} file(s) incomplete.")
        print(f"resume after midnight Pacific: {resume_cmd}")
        return 3
    ok = [r for r in results
          if str(r["status"]).startswith(("regenerated", "skipped"))]
    bad = [r for r in results if r not in ok]
    for r in results:
        extra = ""
        if "reused_batches" in r and r["reused_batches"]:
            extra = f" (reused {r['reused_batches']} batches)"
        print(f"  [{r['status']}{extra}] {r['source']} -> {r.get('target', '')}")
    print(f"done: {len(ok)}/{len(results)} files ok")
    if bad:
        print("resume command: python scripts/migrate_skill_embeddings.py "
              f"--runtime {args.runtime}"
              + (f" --sects {args.sects}" if args.sects else ""))
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate skill embeddings into keyed stores.")
    ap.add_argument("--runtime", required=True, help="runtime YAML (embedding config)")
    ap.add_argument("--sects", default="", help="comma-separated sects (default: all five)")
    ap.add_argument("--dry-run", action="store_true", help="demand estimate only; no API calls, no writes")
    ap.add_argument("--rpm", type=float, default=30.0,
                    help="max API requests per minute (default 30; free-tier quota is 100/min)")
    ap.add_argument("--tpm", type=float, default=25000.0,
                    help="max estimated tokens per minute (default 25000; free-tier quota is 30000/min)")
    ap.add_argument("--rpd", type=float, default=1000.0,
                    help="refuse to start if projected requests exceed this per-day budget (default 1000)")
    ap.add_argument("--token-multiplier", type=float, default=1.0,
                    help="headroom multiplier on the conservative CJK-aware token estimate (default 1.0; must be > 0)")
    args = ap.parse_args()
    if args.token_multiplier <= 0:
        ap.error("--token-multiplier must be > 0")
    if args.rpm <= 0:
        ap.error("--rpm must be > 0")
    if args.tpm is not None and args.tpm <= 0:
        ap.error("--tpm must be > 0")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        # Shard checkpoints are atomic per batch; re-running resumes cleanly.
        print("\ninterrupted by user; completed batches are checkpointed, re-run to resume")
        sys.exit(130)
