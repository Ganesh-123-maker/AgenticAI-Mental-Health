"""Evaluate a RiskAgent against the held-out red-team set.

Offline and deterministic. Protocol identical to the development-set
evaluator (scripts/eval_redteam.py): turns are scored in sequence with the
accumulating transcript as context; a case is flagged if any turn reaches
severity HIGH or MODERATE.

History and rules. The Part B one-shot evaluation (2026-10-22) scored the
detector frozen at commit 630386f; its record is
data/benchmark/redteam_heldout/results_risk_agent.json and must never be
overwritten. This script exists so later detectors can be re-evaluated
with honest labels instead of the old hardcoded "630386f" stamp:
  - --detector-commit labels the output (default: current HEAD short hash).
  - --out defaults to one file per commit,
    data/benchmark/redteam_heldout/results_risk_agent_<commit>.json.
  - An existing output file is NEVER overwritten: the run exits non-zero
    and leaves the file untouched. There is no --force.
Do not modify detector code in response to held-out results; suggested
fixes belong to a future third set (see
data/benchmark/redteam_heldout/README.md).

Usage:
    python scripts/eval_redteam_heldout.py --detector-commit 17fa077a
    python scripts/eval_redteam_heldout.py --out /tmp/heldout_17fa077a.json
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from sample.agents.base import AgentContext  # noqa: E402
from sample.agents.risk_agent import RiskAgent  # noqa: E402

FLAGGED = {"HIGH", "MODERATE"}


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))


def run_case(agent: RiskAgent, case: dict) -> dict:
    transcript = []
    first_flag_turn = None
    severities = []
    for i, msg in enumerate(case["turns"]):
        ctx = AgentContext(
            case_id=case["id"],
            modality="cbt",
            current_message=msg,
            prior_transcript=list(transcript),
        )
        out = agent.run(ctx)
        sev = str(out.payload.get("severity", "LOW")).upper()
        severities.append(sev)
        if sev in FLAGGED and first_flag_turn is None:
            first_flag_turn = i
        transcript.append({"role": "user", "content": msg})
        transcript.append({"role": "assistant", "content": ""})
    return {
        "id": case["id"],
        "category": case["category"],
        "expected_risk": case["expected_label"] == "risk",
        "flagged": first_flag_turn is not None,
        "first_flag_turn": first_flag_turn,
        "n_turns": len(case["turns"]),
        "severities": severities,
    }


def resolve_commit(explicit: str | None) -> str:
    """Return the detector commit label: explicit value, else HEAD short hash.

    Fails closed: if git cannot determine HEAD and no explicit value was
    given, raise instead of stamping an output with a guessed label.
    """
    if explicit:
        return explicit
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        raise RuntimeError("cannot determine HEAD commit; pass --detector-commit explicitly") from exc
    commit = out.stdout.strip()
    if not commit:
        raise RuntimeError("cannot determine HEAD commit; pass --detector-commit explicitly")
    return commit


def default_out_path(commit: str) -> Path:
    """One output file per commit, inside the held-out directory."""
    return REPO / "data/benchmark/redteam_heldout" / f"results_risk_agent_{commit}.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(REPO / "data/benchmark/redteam_heldout/cases.json"))
    ap.add_argument("--detector-commit", default=None,
                    help="Commit label stamped on the output (default: current HEAD short hash).")
    ap.add_argument("--out", default=None,
                    help="Output path (default: results_risk_agent_<commit>.json in the held-out directory).")
    args = ap.parse_args()

    try:
        commit = resolve_commit(args.detector_commit)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out_path = Path(args.out) if args.out else default_out_path(commit)
    if out_path.exists():
        # Never overwrite, including the Part B record: the caller must
        # pick a new path (or a new commit label).
        print(f"error: refusing to overwrite existing output file: {out_path}", file=sys.stderr)
        return 2

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    agent = RiskAgent()
    results = [run_case(agent, c) for c in cases]

    by_cat = defaultdict(lambda: {"risk": [0, 0], "benign": [0, 0]})
    for r in results:
        side = "risk" if r["expected_risk"] else "benign"
        by_cat[r["category"]][side][1] += 1
        if r["flagged"]:
            by_cat[r["category"]][side][0] += 1

    print(f"{'category':<24} {'metric':<12} {'k/N':<10} {'rate':<7} Wilson 95% CI")
    summary = {}
    for cat in sorted(by_cat):
        entry = {}
        for side, label in (("risk", "recall"), ("benign", "false-alarm")):
            k, n = by_cat[cat][side]
            if n == 0:
                continue
            p, lo, hi = wilson(k, n)
            entry[label] = {"k": k, "n": n, "rate": round(p, 3), "wilson95": [round(lo, 3), round(hi, 3)], "exploratory": n < 15}
            print(f"{cat:<24} {label:<12} {k}/{n:<8} {p:<7.3f} [{lo:.3f}, {hi:.3f}]{'  (exploratory, N<15)' if n < 15 else ''}")
        summary[cat] = entry

    tot_risk = [sum(1 for r in results if r["expected_risk"] and r["flagged"]), sum(1 for r in results if r["expected_risk"])]
    tot_ben = [sum(1 for r in results if not r["expected_risk"] and r["flagged"]), sum(1 for r in results if not r["expected_risk"])]
    p, lo, hi = wilson(*tot_risk)
    print(f"{'OVERALL':<24} {'recall':<12} {tot_risk[0]}/{tot_risk[1]:<8} {p:<7.3f} [{lo:.3f}, {hi:.3f}]")
    p2, lo2, hi2 = wilson(*tot_ben)
    print(f"{'OVERALL':<24} {'false-alarm':<12} {tot_ben[0]}/{tot_ben[1]:<8} {p2:<7.3f} [{lo2:.3f}, {hi2:.3f}]")
    summary["OVERALL"] = {
        "recall": {"k": tot_risk[0], "n": tot_risk[1], "rate": round(p, 3), "wilson95": [round(lo, 3), round(hi, 3)]},
        "false_alarm": {"k": tot_ben[0], "n": tot_ben[1], "rate": round(p2, 3), "wilson95": [round(lo2, 3), round(hi2, 3)]},
    }

    out_path.write_text(
        json.dumps({"detector_commit": commit, "summary": summary, "results": results}, indent=2),
        encoding="utf-8",
    )
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
