"""Verify a Gemini skill-embedding migration.

Two modes:

  Record hashes of the ORIGINAL artifacts (run BEFORE any migration):
      python scripts/verify_migration.py --runtime <yaml> --record-hashes hashes.json

  Verify everything (run AFTER migration):
      python scripts/verify_migration.py --runtime <yaml> --verify hashes.json

The verify mode checks, for each of the 15 stage directories:
  1. The original micro_skills.pt is byte-identical to the recorded hash
     (originals must never change).
  2. The provenance-keyed store micro_skills.<model>.<dims>.pt exists.
  3. Its embedded _provenance matches the runtime config (model, dimensions).
  4. Every skill present in the original has both vector fields with the
     configured dimension, all values finite numbers.
  5. No vector space is mixed: keyed-store dims always equal configured dims.

Exit 0 = all checks pass. Exit 1 = any failure (details printed).
Never prints API keys.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEFAULT_REPO_ROOT / "src"))

try:
    import torch
except ImportError:
    torch = None  # type: ignore[assignment]

from sample.io.config_loader import load_runtime_config
from shared.file_utils import resolve_path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


REPO_ROOT = DEFAULT_REPO_ROOT


def _base_files(base_dir: Path) -> list[Path]:
    files: list[Path] = []
    for sect_dir in sorted(base_dir.iterdir()):
        if not sect_dir.is_dir():
            continue
        for stage_dir in sorted(sect_dir.glob("stage*")):
            pt = stage_dir / "micro_skills.pt"
            if pt.exists():
                files.append(pt)
    return files


def _keyed_name(model: str, dim: int) -> str:
    import re

    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", model.strip() or "unknown-model")
    return f"micro_skills.{safe}.{dim}.pt"


def _load_pt(path: Path) -> dict:
    data = torch.load(str(path), weights_only=False)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a dict")
    return data


def cmd_record(args: argparse.Namespace) -> int:
    if torch is None:
        print("FAIL: torch is required")
        return 1
    cfg = load_runtime_config(args.runtime)
    base_dir = resolve_path(cfg.psychagent_skill_base_dir)
    if not base_dir.is_absolute():
        base_dir = (REPO_ROOT / base_dir).resolve()
    files = _base_files(base_dir)
    manifest = {"files": []}
    for pt in files:
        data = _load_pt(pt)
        skills = [k for k, v in data.items() if isinstance(v, dict)]
        manifest["files"].append(
            {
                "path": str(pt.relative_to(REPO_ROOT)),
                "sha256": _sha256(pt),
                "skills": len(skills),
            }
        )
    out = Path(args.record_hashes)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"recorded {len(files)} files -> {out}")
    return 0 if files else 1


def cmd_verify(args: argparse.Namespace) -> int:
    if torch is None:
        print("FAIL: torch is required")
        return 1
    cfg = load_runtime_config(args.runtime)
    base_dir = resolve_path(cfg.psychagent_skill_base_dir)
    if not base_dir.is_absolute():
        base_dir = (REPO_ROOT / base_dir).resolve()
    model = str(_cfg_get(cfg, "psychagent_embedding_model", "gemini-embedding-001")).strip()
    dim = max(1, int(_cfg_get(cfg, "psychagent_embedding_dimensions", 768)))
    provider = str(_cfg_get(cfg, "psychagent_embedding_provider", "gemini")).strip()
    keyed_name = _keyed_name(model, dim)

    manifest = json.loads(Path(args.verify).read_text(encoding="utf-8"))
    expected = {e["path"]: e for e in manifest["files"]}

    failures: list[str] = []
    checked = migrated = 0
    files = _base_files(base_dir)
    print(f"base files found: {len(files)} (expected {len(expected)})")
    if len(files) != len(expected):
        failures.append(f"file count mismatch: found {len(files)}, manifest has {len(expected)}")

    for pt in files:
        rel = str(pt.relative_to(REPO_ROOT))
        checked += 1
        exp = expected.get(rel)
        if exp is None:
            failures.append(f"{rel}: not in hash manifest")
            continue
        actual_hash = _sha256(pt)
        if actual_hash != exp["sha256"]:
            failures.append(f"{rel}: ORIGINAL MODIFIED (hash mismatch)")
            continue
        keyed = pt.parent / keyed_name
        if not keyed.exists():
            failures.append(f"{rel}: keyed store {keyed_name} missing")
            continue
        try:
            store = _load_pt(keyed)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{rel}: keyed store unreadable: {type(exc).__name__}")
            continue
        prov = store.pop("_provenance", None)
        if not isinstance(prov, dict):
            failures.append(f"{rel}: keyed store has no _provenance")
            continue
        if str(prov.get("embedding_model")) != model or int(prov.get("embedding_dimensions", -1)) != dim:
            failures.append(f"{rel}: provenance mismatch {prov.get('embedding_model')}/{prov.get('embedding_dimensions')}")
            continue
        if str(prov.get("embedding_provider")) != provider:
            failures.append(f"{rel}: provenance provider mismatch")
            continue
        base_skills = {k for k, v in _load_pt(pt).items() if isinstance(v, dict)}
        store_skills = {k for k, v in store.items() if isinstance(v, dict)}
        if base_skills != store_skills:
            failures.append(f"{rel}: skill id sets differ (base {len(base_skills)}, store {len(store_skills)})")
            continue
        bad = 0
        for sid, skill in store.items():
            if not isinstance(skill, dict):
                continue
            for field in ("embedding_to_merge", "embedding_to_retrive"):
                vec = skill.get(field)
                if not isinstance(vec, list) or len(vec) != dim:
                    bad += 1
                    break
                if not all(isinstance(x, float) and math.isfinite(x) for x in vec):
                    bad += 1
                    break
        if bad:
            failures.append(f"{rel}: {bad} skills with invalid vectors")
            continue
        migrated += 1

    print(f"checked={checked} valid_stores={migrated} failures={len(failures)}")
    for f in failures:
        print("  FAIL:", f)
    print("VERIFY:", "PASS" if not failures and migrated == checked and checked else "FAIL")
    return 0 if (not failures and migrated == checked and checked > 0) else 1


def _cfg_get(cfg, name: str, default):
    return getattr(cfg, name, default)


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify a Gemini embedding migration.")
    ap.add_argument("--runtime", required=True)
    ap.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--record-hashes", metavar="MANIFEST", help="record original hashes")
    g.add_argument("--verify", metavar="MANIFEST", help="verify against manifest")
    args = ap.parse_args()
    global REPO_ROOT
    REPO_ROOT = Path(args.repo_root).resolve()
    return cmd_record(args) if args.record_hashes else cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
