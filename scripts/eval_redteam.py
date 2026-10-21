"""Evaluate the rule-based RiskAgent against the synthetic red-team set.

Offline and deterministic: the RiskAgent is rule-based, so no model calls are
made. A case counts as FLAGGED when the agent severity is HIGH or MODERATE.
For multi-turn cases every turn is evaluated in sequence with transcript
context; the case is flagged if any turn flags, and the first flagged turn is
recorded.

Reports per-category recall (risk-labeled cases) and false-alarm rate
(benign-labeled cases) with Wilson 95% confidence intervals. Categories with
N < 15 are exploratory by the study's pre-registration convention.

Usage:
    python scripts/eval_redteam.py [--cases data/benchmark/redteam/cases.json]
                                   [--out data/benchmark/redteam/results_risk_agent.json]
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
    turns = case.get("turns") or [case.get("message", "")]
    transcript = []
    first_flag_turn = None
    severities = []
    for i, msg in enumerate(turns):
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
        "expected_risk": case["expected_risk"],
        "flagged": first_flag_turn is not None,
        "first_flag_turn": first_flag_turn,
        "n_turns": len(turns),
        "severities": severities,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(REPO / "data/benchmark/redteam/cases.json"))
    ap.add_argument("--out", default=str(REPO / "data/benchmark/redteam/results_risk_agent.json"))
    args = ap.parse_args()

    doc = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases = doc["cases"]
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

    out_doc = {
        "detector": "RiskAgent (rule-based), flagged = severity in {HIGH, MODERATE}",
        "cases_file": str(args.cases),
        "summary": summary,
        "overall": {
            "recall": {"k": tot_risk[0], "n": tot_risk[1]},
            "false_alarm": {"k": tot_ben[0], "n": tot_ben[1]},
        },
        "per_case": results,
    }
    Path(args.out).write_text(json.dumps(out_doc, indent=2), encoding="utf-8")
    print("\nwrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
