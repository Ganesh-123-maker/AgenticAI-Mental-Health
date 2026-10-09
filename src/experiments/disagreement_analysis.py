"""Agent-disagreement / belief-revision analysis from stored execution trails.

Disagreement signals are defined ONLY from fields actually present in the
stored trails (no invented definitions):

  D1. clarification_loop_revision: the Clarification -> Reassessment loop ran
      and the Orchestrator's route CHANGED between its first and final call.
      (Initial assessment vs post-clarification reassessment disagreeing.)
  D2. supervisor_intervention: SafetySupervisor verdict != ALLOW
      (REVISE / RE-ROUTE / ESCALATE). The supervisor disagreed with the
      drafted response or routing.
  D3. risk_overrode_uncertainty (descriptive only, n too small to test):
      risk severity HIGH while uncertainty status was CLEAR.

Downstream outcomes (per case, from stored layer2 metrics and the benchmark):
  O1. routing_correct: final orchestrator route == benchmark expected_route.
  O2. routing_improved_by_loop: paired first-route vs final-route correctness
      (McNemar exact) — "does clarification improve routing decisions?"
  O3. safety_ok: safety_f1 == 1.0.  O4. false_certain: false_certainty_rate == 1.0.

For D2 (unpaired groups, tiny n) Fisher's exact test is used and the lack of
power is reported honestly.

Run:  python src/experiments/disagreement_analysis.py
Writes: data/eval_outputs_multi_agent/disagreement_analysis.json
"""

from __future__ import annotations

import glob
import json
import math
import os
import sys
from typing import Dict, List, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TREE = os.path.join(REPO_ROOT, "data", "eval_outputs_multi_agent", "System_F")
BENCH = os.path.join(REPO_ROOT, "data", "benchmark", "ambiguous_cases")


def load_trails() -> List[Dict]:
    cases = []
    for fp in sorted(glob.glob(os.path.join(TREE, "*.json"))):
        if os.path.basename(fp) == "summary.json":
            continue
        with open(fp, encoding="utf-8") as fh:
            cases.append(json.load(fh))
    return cases


def load_expected_routes() -> Dict[str, str]:
    exp = {}
    for fp in glob.glob(os.path.join(BENCH, "*", "*.json")):
        with open(fp, encoding="utf-8") as fh:
            c = json.load(fh)
        exp[c["case_id"]] = str(c.get("expected_route", "")).upper()
    return exp


def trail_signals(case: Dict) -> Dict:
    """Extract disagreement-relevant signals from one stored trail."""
    sig: Dict[str, Optional[str]] = {
        "uncertainty_status": None, "risk_severity": None,
        "first_route": None, "final_route": None, "supervisor_verdict": None,
    }
    routes = []
    for s in case.get("trail", []):
        ag = s.get("agent")
        p = s.get("payload", {}) or {}
        if ag == "uncertainty_agent":
            sig["uncertainty_status"] = str(p.get("status", "")).upper()
        elif ag == "risk_agent":
            sig["risk_severity"] = str(p.get("severity", "")).upper()
        elif ag == "orchestrator":
            r = str(s.get("route") or p.get("route") or "").upper()
            if r:
                routes.append(r)
        elif ag == "safety_supervisor" and "supervision_turn" in str(s.get("step", "")):
            sig["supervisor_verdict"] = str(s.get("verdict") or p.get("verdict") or "").upper()
    if routes:
        sig["first_route"], sig["final_route"] = routes[0], routes[-1]
    return sig


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(2.0 * sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n), 1.0)


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher's exact p for [[a,b],[c,d]] via the hypergeometric."""
    n = a + b + c + d
    if n == 0:
        return 1.0
    def hg(i: int) -> float:
        # P(X=i) for X ~ Hypergeometric(n, a+c, a+b)
        return (math.comb(a + b, i) * math.comb(c + d, (a + c) - i)) / math.comb(n, a + c)
    p_obs = hg(a)
    # two-sided: sum probabilities of tables no more likely than observed
    lo, hi = max(0, (a + c) - (c + d)), min(a + b, a + c)
    return min(sum(hg(i) for i in range(lo, hi + 1) if hg(i) <= p_obs + 1e-12), 1.0)


def main() -> None:
    cases = load_trails()
    expected = load_expected_routes()
    out: Dict = {"n_cases": len(cases), "signals": {}, "findings": []}

    rows = []
    for case in cases:
        sig = trail_signals(case)
        cid = case["case_id"]
        exp = expected.get(cid)
        l2 = case.get("layer2_metrics", {}) or {}
        rows.append({
            "case_id": cid,
            "first_route": sig["first_route"], "final_route": sig["final_route"],
            "expected_route": exp,
            "uncertainty_status": sig["uncertainty_status"],
            "risk_severity": sig["risk_severity"],
            "supervisor_verdict": sig["supervisor_verdict"],
            "first_correct": sig["first_route"] == exp if sig["first_route"] else None,
            "final_correct": sig["final_route"] == exp if sig["final_route"] else None,
            "safety_ok": (l2.get("safety_f1") or 0) >= 1.0,
            "false_certain": (l2.get("false_certainty_rate") or 0) >= 1.0,
        })
    out["rows"] = rows

    # ---- D1: clarification-loop revision -> paired first vs final routing ----
    a = b = cc = d = 0
    for r in rows:
        if r["first_correct"] is None or r["final_correct"] is None:
            continue
        if r["first_correct"] and r["final_correct"]:
            a += 1
        elif r["first_correct"] and not r["final_correct"]:
            b += 1
        elif not r["first_correct"] and r["final_correct"]:
            cc += 1
        else:
            d += 1
    n = a + b + cc + d
    p = mcnemar_exact(b, cc)
    diff = (cc - b) / n if n else 0.0
    se = math.sqrt(max(((b + cc) - (cc - b) ** 2 / n) / n ** 2, 0.0)) if n else 0.0
    out["signals"]["clarification_loop_revision"] = {
        "definition": "orchestrator route changed between first and final call "
                      "(Clarification -> Reassessment loop ran)",
        "n_paired": n,
        "contingency_first_vs_final_correct": {
            "both_correct": a, "first_only": b, "final_only": cc, "neither": d},
        "first_route_accuracy": round((a + b) / n, 4) if n else None,
        "final_route_accuracy": round((a + cc) / n, 4) if n else None,
        "improvement": round(diff, 4),
        "improvement_95ci": [round(diff - 1.96 * se, 4), round(diff + 1.96 * se, 4)],
        "mcnemar_exact_p_two_sided": round(p, 4),
    }

    # ---- D2: supervisor intervention vs downstream outcomes (Fisher) ----
    for outcome, label in [("final_correct", "routing failure"),
                           ("safety_ok", "safety failure"),
                           ("false_certain", "false certainty")]:
        # rows: intervened (verdict != ALLOW) vs allowed
        ia_ok = ia_bad = al_ok = al_bad = 0
        for r in rows:
            v = r["supervisor_verdict"]
            if v is None:
                continue
            intervened = (v != "ALLOW")
            good = bool(r[outcome]) if outcome != "false_certain" else not bool(r[outcome])
            if intervened and good:
                ia_ok += 1
            elif intervened and not good:
                ia_bad += 1
            elif not intervened and good:
                al_ok += 1
            else:
                al_bad += 1
        p = fisher_exact(ia_ok, ia_bad, al_ok, al_bad)
        out["signals"].setdefault("supervisor_intervention", {})[outcome] = {
            "definition": "supervisor verdict != ALLOW (REVISE/RE-ROUTE/ESCALATE)",
            "contingency_intervened_vs_allowed_x_good_vs_bad": {
                "intervened_good": ia_ok, "intervened_bad": ia_bad,
                "allowed_good": al_ok, "allowed_bad": al_bad},
            "fisher_exact_p_two_sided": round(p, 4),
        }

    # ---- D3: risk overriding uncertainty (descriptive) ----
    overrides = [r for r in rows
                 if r["risk_severity"] == "HIGH" and r["uncertainty_status"] == "CLEAR"]
    out["signals"]["risk_overrode_uncertainty"] = {
        "definition": "risk severity HIGH while uncertainty status CLEAR",
        "n": len(overrides),
        "cases": [{"case_id": r["case_id"], "final_route": r["final_route"],
                   "supervisor_verdict": r["supervisor_verdict"],
                   "final_correct": r["final_correct"]} for r in overrides],
    }

    out_path = os.path.join(os.path.dirname(TREE), "disagreement_analysis.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    d1 = out["signals"]["clarification_loop_revision"]
    print(f"D1 clarification-loop revision: N={d1['n_paired']} paired | "
          f"first-route acc={d1['first_route_accuracy']} final-route acc={d1['final_route_accuracy']} | "
          f"improvement={d1['improvement']} 95%CI={d1['improvement_95ci']} | McNemar p={d1['mcnemar_exact_p_two_sided']}")
    for oc, r in out["signals"]["supervisor_intervention"].items():
        t = r["contingency_intervened_vs_allowed_x_good_vs_bad"]
        print(f"D2 supervisor intervention vs {oc}: intervened {t['intervened_good']}/{t['intervened_bad']} "
              f"(good/bad) vs allowed {t['al_ok'] if 'al_ok' in t else t['allowed_good']}/{t['allowed_bad']} | Fisher p={r['fisher_exact_p_two_sided']}")
    print(f"D3 risk-overrode-uncertainty: n={out['signals']['risk_overrode_uncertainty']['n']} (descriptive only)")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    sys.exit(main())
