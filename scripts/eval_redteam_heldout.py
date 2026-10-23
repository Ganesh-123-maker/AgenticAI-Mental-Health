"""Evaluate the frozen RiskAgent against the held-out red-team set, ONCE.

Offline and deterministic. Protocol identical to the development-set
evaluator (scripts/eval_redteam.py): turns are scored in sequence with the
accumulating transcript as context; a case is flagged if any turn reaches
severity HIGH or MODERATE.

The detector is frozen at commit 630386f (see
data/benchmark/redteam_heldout/README.md). Do not modify detector code in
response to these results; suggested fixes belong to a future third set.

Usage:
    python scripts/eval_redteam_heldout.py
"""

from __future__ import annotations

import argparse
import json
import math
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(REPO / "data/benchmark/redteam_heldout/cases.json"))
    ap.add_argument("--out", default=str(REPO / "data/benchmark/redteam_heldout/results_risk_agent.json"))
    args = ap.parse_args()

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

    Path(args.out).write_text(
        json.dumps({"detector_frozen_at": "630386f", "summary": summary, "results": results}, indent=2),
        encoding="utf-8",
    )
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
