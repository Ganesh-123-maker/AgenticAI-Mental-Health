"""Statistical analysis of paired system comparisons using existing evaluation data.

Comparisons (pre-registered before running):
  1. False certainty: System_F vs ablation_no_uncertainty (per-case
     false_certainty_rate, binary 0/1). Tests whether the UncertaintyAgent
     reduces false-certainty — the core of the research question.
  2. Safety: System_F vs ablation_no_risk (per-case safety_f1, binarized as
     1.0 = pass, <1.0 = fail). Tests whether the RiskAgent reduces safety
     failures.

Both systems were evaluated on the same benchmark cases, so observations are
PAIRED by case_id and the outcome is BINARY per case. The correct test is
McNemar's exact test (two-sided binomial on discordant pairs) — not a t-test,
which assumes continuous approximately-normal differences.

Effect size: difference in paired proportions (sys2 - sys1) with a Wald 95%
confidence interval. With 2 comparisons, Bonferroni correction gives a
per-test alpha of 0.025.

Run:  python src/experiments/statistical_analysis.py [--tree n33|n25|both]
Writes: data/eval_outputs_multi_agent/statistical_analysis.json
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TREES = {
    "n33": os.path.join(REPO_ROOT, "data", "eval_outputs_multi_agent"),
    "n25": os.path.join(REPO_ROOT, "data", "research_evaluation", "system_outputs"),
}


def load_paired(base: str, sys1: str, sys2: str, metric: str) -> List[Tuple[str, float, float]]:
    """Load per-case metric values paired by case_id. Skips cases where the
    metric is None (not applicable) in either system."""
    vals: Dict[str, Dict[str, Optional[float]]] = {}
    for sys in (sys1, sys2):
        for fp in glob.glob(os.path.join(base, sys, "*.json")):
            if os.path.basename(fp) == "summary.json":
                continue
            with open(fp, encoding="utf-8") as fh:
                c = json.load(fh)
            v = c.get("layer2_metrics", {}).get(metric)
            vals.setdefault(c["case_id"], {})[sys] = v
    pairs = []
    for cid in sorted(vals):
        x, y = vals[cid].get(sys1), vals[cid].get(sys2)
        if x is not None and y is not None:
            pairs.append((cid, float(x), float(y)))
    return pairs


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value via the binomial distribution on the
    b + c discordant pairs (H0: each discordant pair favors either system
    with probability 0.5)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(2.0 * tail, 1.0)


def analyze(pairs: List[Tuple[str, float, float]], sys1: str, sys2: str,
            metric: str, description: str) -> Dict:
    """McNemar analysis on binarized paired outcomes (1.0 vs <1.0)."""
    a = b = cc = d = 0
    for _, x, y in pairs:
        xb, yb = (1.0 if x >= 1.0 else 0.0), (1.0 if y >= 1.0 else 0.0)
        if xb == 1.0 and yb == 1.0:
            a += 1
        elif xb == 1.0 and yb == 0.0:
            b += 1
        elif xb == 0.0 and yb == 1.0:
            cc += 1
        else:
            d += 1
    n = a + b + cc + d
    p = mcnemar_exact(b, cc)
    # Effect: paired difference in "positive" (1.0) rates, sys2 - sys1.
    diff = (cc - b) / n if n else 0.0
    disc = b + cc
    var = ((disc - (cc - b) ** 2 / n) / n ** 2) if n else 0.0
    se = math.sqrt(max(var, 0.0))
    return {
        "description": description,
        "metric": metric,
        "systems": [sys1, sys2],
        "n_paired": n,
        "contingency": {"both_positive": a, "sys1_only": b, "sys2_only": cc, "neither": d},
        "sys1_positive_rate": round((a + b) / n, 4) if n else None,
        "sys2_positive_rate": round((a + cc) / n, 4) if n else None,
        "diff_sys2_minus_sys1": round(diff, 4),
        "diff_95ci": [round(diff - 1.96 * se, 4), round(diff + 1.96 * se, 4)],
        "mcnemar_exact_p_two_sided": round(p, 4),
        "discordant_pairs": disc,
    }


COMPARISONS = [
    ("System_F", "ablation_no_uncertainty", "false_certainty_rate",
     "False certainty: does the UncertaintyAgent reduce false-certain responses? "
     "(positive = false-certain on the case)"),
    ("System_F", "ablation_no_risk", "safety_f1",
     "Safety: does the RiskAgent reduce safety failures? "
     "(positive = safety_f1 == 1.0 on the case)"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description="Paired statistical analysis of evaluation data")
    ap.add_argument("--tree", choices=["n33", "n25", "both"], default="both")
    args = ap.parse_args()

    trees = [args.tree] if args.tree != "both" else ["n33", "n25"]
    results: Dict = {"trees": {}, "method": "McNemar exact (two-sided binomial on discordant pairs); "
                                            "Bonferroni per-test alpha = 0.025 for 2 comparisons"}
    for t in trees:
        base = TREES[t]
        tree_res = []
        for s1, s2, metric, desc in COMPARISONS:
            pairs = load_paired(base, s1, s2, metric)
            if not pairs:
                print(f"[{t}] {s1} vs {s2} ({metric}): no paired data, skipped")
                continue
            r = analyze(pairs, s1, s2, metric, desc)
            r["tree"] = t
            tree_res.append(r)
            print(f"[{t}] {desc.split('?')[0]}?")
            print(f"     N={r['n_paired']} paired | {s1}={r['sys1_positive_rate']} "
                  f"{s2}={r['sys2_positive_rate']} | diff={r['diff_sys2_minus_sys1']} "
                  f"95%CI={r['diff_95ci']} | McNemar exact p={r['mcnemar_exact_p_two_sided']} "
                  f"(discordant={r['discordant_pairs']})")
        results["trees"][t] = tree_res

    out = os.path.join(TREES["n33"], "statistical_analysis.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    sys.exit(main())
