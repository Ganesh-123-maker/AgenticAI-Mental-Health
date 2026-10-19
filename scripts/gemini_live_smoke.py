"""Minimal bounded live Gemini embedding smoke test.

Sends exactly TWO synthetic texts (one batch) to the configured embedding
provider and validates the response. Costs a negligible amount of quota;
sends text to Google — use only synthetic text, never personal data.

The API key is read from the environment variable named in the runtime config.
It is never printed, logged, or written to disk by this script.

Usage (PowerShell):
    python scripts/gemini_live_smoke.py --runtime configs/runtime/multi_agent_gemini.yaml

Exit 0 = live embedding works and vectors validate.
Exit non-zero = failure; the error message never contains the key.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sample.io.config_loader import load_runtime_config
from sample.skill_manager import SkillManager


class _LiveBackend:
    """Minimal non-dummy backend: marks the run as live."""

    is_offline = False

    async def chat_text(self, messages, **kwargs):
        raise RuntimeError("smoke test never calls the chat backend")


def _redact(msg: str, key: str) -> str:
    return msg.replace(key, "<redacted>") if key else msg


async def _run(runtime_path: str) -> int:
    cfg = load_runtime_config(runtime_path)
    env_name = str(cfg.psychagent_embedding_api_key_env).strip()
    key = os.environ.get(env_name, "").strip()
    print(f"key variable '{env_name}': {'set' if key else 'NOT SET'}")
    if not key:
        print("FAIL: set the key environment variable first (value never printed)")
        return 2

    expected_dim = max(1, int(cfg.psychagent_embedding_dimensions))
    model = str(cfg.psychagent_embedding_model)
    print(f"provider={cfg.psychagent_embedding_provider} model={model} "
          f"dim={expected_dim} timeout={cfg.psychagent_embedding_timeout_sec}s")

    mgr = SkillManager(_LiveBackend(), cfg)
    try:
        texts = ["hello world, this is a synthetic smoke test",
                 "the quick brown fox jumps over the lazy dog"]
        vecs = await mgr._embed_by_api(texts, task_type="RETRIEVAL_QUERY")
    except Exception as exc:  # noqa: BLE001 - report, redacted
        print(f"FAIL: {type(exc).__name__}: {_redact(str(exc), key)[:300]}")
        return 1
    finally:
        await mgr.aclose()

    checks = {
        "count == 2": len(vecs) == 2,
        f"dim == {expected_dim}": all(len(v) == expected_dim for v in vecs),
        "all finite numbers": all(isinstance(x, float) and math.isfinite(x) for v in vecs for x in v),
        "not all zero (real inference)": any(x != 0.0 for v in vecs for x in v),
    }
    ok = True
    for name, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print("LIVE SMOKE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Minimal live Gemini embedding smoke test.")
    ap.add_argument("--runtime", required=True, help="runtime YAML with embedding config")
    return asyncio.run(_run(ap.parse_args().runtime))


if __name__ == "__main__":
    sys.exit(main())
