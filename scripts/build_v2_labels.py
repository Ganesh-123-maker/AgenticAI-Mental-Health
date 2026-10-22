"""Recompute v2 uncertainty labels from the full-vs-ambiguous context diff.

Rule (structural, stated in advance): a case is UNCERTAIN iff the ambiguous
context withholds information the full context has - i.e. at least one leaf
field that is non-empty in full_context is empty or absent in
ambiguous_context. Otherwise CLEAR. Risk labels are never assigned here:
risk_label is UNVERIFIED for every case (no human-reviewed label exists).
"""
import csv, glob, json, math
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "data/benchmark/v2"

def flat(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flat(v, key + "."))
        else:
            out[key] = v
    return out

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / den
    return (p, max(0.0, c - h), min(1.0, c + h))

rows, sheet = [], []
agree = disagree = 0
detail = {"recomputed_UNCERTAIN": 0, "recomputed_CLEAR": 0}
confusion = {}
for f in sorted(glob.glob(str(REPO / "data/benchmark/ambiguous_cases/*/*.json"))):
    d = json.loads(Path(f).read_text(encoding="utf-8"))
    ff, af = flat(d["full_context"]), flat(d["ambiguous_context"])
    removed = [k for k in ff if str(ff[k]).strip() not in ("", "None") and str(af.get(k, "")).strip() in ("", "None")]
    label = "UNCERTAIN" if removed else "CLEAR"
    detail[f"recomputed_{label}"] += 1
    stored = d["expected_route"]
    # agreement is about the uncertainty dimension only: stored HIGH-RISK is a
    # risk route, not an uncertainty judgement, so it maps to "not UNCERTAIN"
    stored_unc = "UNCERTAIN" if stored == "UNCERTAIN" else "NOT_UNCERTAIN"
    recomp = "UNCERTAIN" if label == "UNCERTAIN" else "NOT_UNCERTAIN"
    ok = stored_unc == recomp
    agree += ok; disagree += (not ok)
    confusion[(stored, label)] = confusion.get((stored, label), 0) + 1
    rows.append({
        "case_id": d["case_id"],
        "uncertainty_label": label,
        "risk_label": "UNVERIFIED",
        "provenance": "uncertainty: recomputed from full-vs-ambiguous diff, rule v1 (withheld-field); risk: UNVERIFIED - no human-reviewed label exists",
    })
    excerpt = str(d["full_context"].get("basic_info", {}).get("main_problem", ""))[:300]
    sheet.append({"case_id": d["case_id"], "context_excerpt": excerpt, "reviewer_risk_label": ""})

with open(OUT / "labels.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["case_id", "uncertainty_label", "risk_label", "provenance"]); w.writeheader(); w.writerows(rows)
with open(OUT / "risk_review_sheet.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["case_id", "context_excerpt", "reviewer_risk_label"]); w.writeheader(); w.writerows(sheet)

n = agree + disagree
p, lo, hi = wilson(agree, n)
print(f"cases: {n} | recomputed: {detail}")
print(f"agreement recomputed-vs-stored-route: {agree}/{n} = {p:.3f} [{lo:.3f}, {hi:.3f}] Wilson 95%")
print("confusion (stored_route, recomputed_label):", dict(sorted(confusion.items())))
print("wrote labels.csv + risk_review_sheet.csv to", OUT)
