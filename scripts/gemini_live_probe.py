"""Minimal live Gemini connectivity probe (requires explicit user approval).

Sends ONE tiny synthetic embedding request (no real data, no mental-health
content). Never prints the API key. Records only sanitized metadata.

Usage (PowerShell):
    $env:GEMINI_API_KEY = "..."   # set once per session; never echo it
    python scripts/gemini_live_probe.py --runtime configs/runtime/multi_agent_gemini.yaml

Exit 0: probe succeeded (vector OK). Exit 1: probe failed (see sanitized reason).
Exit 2: configuration problem (key missing, etc.). Makes exactly 1 API call.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sample.io.config_loader import load_runtime_config
from sample.skill_manager import SkillManager


class _NullBackend:
    is_offline = False

    async def chat_text(self, messages, **kwargs):
        raise RuntimeError("probe never calls the chat backend")


async def _probe(runtime_path: str) -> int:
    cfg = load_runtime_config(runtime_path)
    env_name = str(cfg.psychagent_embedding_api_key_env).strip()
    if not os.environ.get(env_name, "").strip():
        print(f"FAIL: '{env_name}' is not set in the process environment (value never printed)")
        return 2
    if str(cfg.psychagent_embedding_provider).strip().lower() != "gemini":
        print("FAIL: provider is not 'gemini' in the runtime config")
        return 2

    mgr = SkillManager(_NullBackend(), cfg)
    dim = max(1, int(cfg.psychagent_embedding_dimensions))
    model = str(cfg.psychagent_embedding_model).strip()
    texts = ["synthetic connectivity probe"]

    start = time.time()
    try:
        vecs = await mgr._embed_by_api(texts, task_type="RETRIEVAL_QUERY")
    except Exception as exc:  # noqa: BLE001 - report sanitized failure
        safe = str(exc)
        key = os.environ.get(env_name, "")
        if key:
            safe = safe.replace(key, "<redacted>")
        print(f"PROBE FAILED: {type(exc).__name__}: {safe[:400]}")
        print(f"model={model} dim={dim} elapsed={time.time()-start:.1f}s")
        return 1
    elapsed = time.time() - start

    ok = (
        isinstance(vecs, list) and len(vecs) == 1
        and isinstance(vecs[0], list) and len(vecs[0]) == dim
        and all(isinstance(x, float) and math.isfinite(x) for x in vecs[0])
    )
    print(f"model={model} dim={dim} elapsed={elapsed:.1f}s")
    print(f"vector: count=1 dimensions={len(vecs[0]) if vecs else 0} "
          f"all_finite={ok}")
    if ok:
        print("PROBE PASSED: 1 API call, 768-dim finite vector returned")
        return 0
    print("PROBE FAILED: vector failed validation")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Minimal live Gemini probe (1 API call).")
    ap.add_argument("--runtime", required=True)
    args = ap.parse_args()
    try:
        return asyncio.run(_probe(args.runtime))
    except KeyboardInterrupt:
        print("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
