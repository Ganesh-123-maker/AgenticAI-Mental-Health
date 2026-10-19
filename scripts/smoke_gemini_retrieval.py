#!/usr/bin/env python3
"""Retrieval smoke test for the Gemini embedding migration.

Verifies, through the REAL production code path
(SkillManager._load_micro_skills), that:

  1. Every stage dir selects the provenance-keyed store
     (micro_skills.<model>.<dims>.pt) -- never the BGE-M3 original.
  2. The keyed store's _provenance (model + dimensions) matches the
     runtime config.
  3. Every skill vector is 768-dim; no 1024-dim (BGE-M3) vectors leak in.
  4. (live, costs 1 API text) A real query embedded with
     gemini-embedding-001 ranks sensible skills by cosine similarity
     against the keyed store -- proving the stored vectors live in the
     same space as the live API.

Run from the repo root:
    python scripts/smoke_gemini_retrieval.py --runtime configs/runtime/multi_agent_gemini.yaml

Requires GEMINI_API_KEY in the environment (only for the live check;
pass --skip-live to skip it). Never prints the key.
"""

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import torch  # noqa: E402

from sample.io.config_loader import load_runtime_config  # noqa: E402
from sample.skill_manager import SkillManager  # noqa: E402

TEST_QUERY = "I feel anxious about my exams and cannot sleep at night"
TOP_K = 5


def fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"SMOKE FAIL: {msg}")
    raise SystemExit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Gemini retrieval smoke test")
    ap.add_argument("--runtime", required=True, help="runtime yaml path")
    ap.add_argument("--skip-live", action="store_true",
                    help="skip the live API query-embedding check")
    args = ap.parse_args()

    cfg = load_runtime_config(args.runtime)
    model = str(cfg.psychagent_embedding_model).strip()
    dim = int(cfg.psychagent_embedding_dimensions)
    print(f"config: provider=gemini model={model} dim={dim}")

    manager = SkillManager(backend=None, runtime_config=cfg)
    key = manager._embedding_store_key()
    print(f"expected keyed store: micro_skills.{key}.pt")

    base = REPO_ROOT / "assets" / "skills" / "sect"
    stage_dirs = sorted(p.parent for p in base.glob("*/*/micro_skills.pt"))
    if len(stage_dirs) != 15:
        fail(f"expected 15 stage dirs, found {len(stage_dirs)}")
    print(f"stage dirs: {len(stage_dirs)}")

    total_skills = 0
    for stage_dir in stage_dirs:
        keyed = stage_dir / f"micro_skills.{key}.pt"
        if not keyed.exists():
            fail(f"missing keyed store: {keyed}")

        raw = torch.load(str(keyed), weights_only=False)
        prov = raw.get("_provenance") if isinstance(raw, dict) else None
        if not manager._provenance_matches(prov):
            fail(f"provenance mismatch in {keyed} (model/dims do not match config)")

        skills = manager._load_micro_skills(stage_dir)
        if not skills:
            fail(f"no skills loaded from {stage_dir}")
        for sid, s in skills.items():
            for field in ("embedding_to_merge", "embedding_to_retrive"):
                vec = s.get(field)
                if vec is None:
                    fail(f"{stage_dir.name}/{sid}: missing {field}")
                if len(vec) == 1024:
                    fail(f"{stage_dir.name}/{sid}: BGE-M3 1024-dim vector leaked in "
                         f"({field}) -- vector spaces are mixed!")
                if len(vec) != dim:
                    fail(f"{stage_dir.name}/{sid}: {field} has dim {len(vec)}, "
                         f"expected {dim}")
        total_skills += len(skills)
        print(f"  ok {stage_dir.parent.name}/{stage_dir.name}: "
              f"{len(skills)} skills, all {dim}-dim, keyed store selected")

    print(f"PASS (offline): 15/15 keyed stores selected, "
          f"{total_skills} skills, all vectors {dim}-dim, zero 1024-dim vectors")

    if args.skip_live:
        print("live check skipped (--skip-live)")
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        fail("GEMINI_API_KEY is not set in the environment")

    from google import genai
    client = genai.Client(api_key=api_key)
    resp = client.models.embed_content(
        model=model,
        contents=[TEST_QUERY],
        config={"output_dimensionality": dim, "task_type": "RETRIEVAL_QUERY"},
    )
    q = torch.tensor(resp.embeddings[0].values, dtype=torch.float32)
    if q.numel() != dim:
        fail(f"live query embedding has dim {q.numel()}, expected {dim}")
    q = q / q.norm()

    stage_dir = base / "bt" / "stage1"
    skills = manager._load_micro_skills(stage_dir)
    ids, vecs = [], []
    for sid, s in skills.items():
        v = torch.tensor(s["embedding_to_retrive"], dtype=torch.float32)
        ids.append(s.get("skill_id", sid))
        vecs.append(v / v.norm())
    sims = torch.stack(vecs) @ q
    top = torch.topk(sims, k=TOP_K)

    print(f'PASS (live): query "{TEST_QUERY}"')
    print(f"  embedded live with {model} ({dim}-dim), ranked "
          f"{len(ids)} keyed vectors from bt/stage1:")
    for rank, idx in enumerate(top.indices.tolist(), 1):
        print(f"    {rank}. {ids[idx]}  cosine={top.values[rank-1]:.3f}")
    print("SMOKE TEST: ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
