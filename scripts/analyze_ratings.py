"""Analyze expert ratings from a blinded review packet.

Inputs:
  --ratings  CSV with one row per (rater, packet_case):
             rater_id, packet_case, appropriateness_a, appropriateness_b,
             handling_missing_information_a, handling_missing_information_b,
             handling_risk_a, handling_risk_b, overall_preference (A/B/tie)
  --key      the packet key JSON produced by make_review_packet.py
  --judge    optional CSV of automated-judge scores with the same columns
             (rater_id fixed to "judge") to compare raters against the judge.

Computes, per scale:
  - Cohen's kappa between the first two raters (exact score agreement)
  - Quadratic-weighted kappa between the first two raters (ordinal scales)
  - Rater-vs-judge Cohen's kappa when --judge is given
And for overall preference after unblinding with the key:
  - Sign test (two-sided, ties excluded) on S1-vs-P1 preferences pooled
    across raters.

Pure standard library. This script analyzes ratings; it never creates them.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

SCALES = ["appropriateness", "handling_missing_information", "handling_risk"]


def cohen_kappa(pairs: list) -> float:
    n = len(pairs)
    if n == 0:
        return float("nan")
    po = sum(1 for a, b in pairs if a == b) / n
    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    cats = set(ca) | set(cb)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def weighted_kappa(pairs: list, lo: int = 1, hi: int = 5) -> float:
    n = len(pairs)
    if n == 0:
        return float("nan")
    k = hi - lo
    def w(a, b):
        return 1 - ((a - b) ** 2) / (k ** 2)
    po = sum(w(a, b) for a, b in pairs) / n
    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    pe = sum(w(a, b) * (ca[a] / n) * (cb[b] / n) for a in ca for b in cb)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def sign_test(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def load_ratings(path: str) -> dict:
    by_rater = defaultdict(dict)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_rater[row["rater_id"]][int(row["packet_case"])] = row
    return by_rater


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratings", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--judge", default=None)
    args = ap.parse_args()

    key = json.loads(Path(args.key).read_text(encoding="utf-8"))["mapping"]
    by_rater = load_ratings(args.ratings)
    raters = sorted(by_rater)
    print(f"raters: {raters}")

    if len(raters) >= 2:
        r1, r2 = raters[0], raters[1]
        common = sorted(set(by_rater[r1]) & set(by_rater[r2]))
        print(f"inter-rater agreement between {r1} and {r2} on {len(common)} shared cases:")
        for scale in SCALES:
            for side in ("a", "b"):
                pairs = [
                    (int(by_rater[r1][c][f"{scale}_{side}"]), int(by_rater[r2][c][f"{scale}_{side}"]))
                    for c in common
                    if by_rater[r1][c].get(f"{scale}_{side}") and by_rater[r2][c].get(f"{scale}_{side}")
                ]
                if pairs:
                    print(f"  {scale}_{side}: N={len(pairs)} Cohen k={cohen_kappa(pairs):.3f} weighted k={weighted_kappa(pairs):.3f}")

    if args.judge:
        judge = load_ratings(args.judge).get("judge", {})
        for r in raters:
            common = sorted(set(by_rater[r]) & set(judge))
            for scale in SCALES:
                for side in ("a", "b"):
                    pairs = [
                        (int(by_rater[r][c][f"{scale}_{side}"]), int(judge[c][f"{scale}_{side}"]))
                        for c in common
                        if by_rater[r][c].get(f"{scale}_{side}") and judge[c].get(f"{scale}_{side}")
                    ]
                    if pairs:
                        print(f"  {r} vs judge {scale}_{side}: N={len(pairs)} Cohen k={cohen_kappa(pairs):.3f}")

    # overall preference, unblinded via the key
    s1_wins = p1_wins = ties = 0
    for r in raters:
        for c, row in by_rater[r].items():
            pref = (row.get("overall_preference") or "").strip()
            if not pref:
                continue
            if pref.lower() == "tie":
                ties += 1
            else:
                winner = key[str(c)]["a_is"] if pref.upper() == "A" else key[str(c)]["b_is"]
                if winner == "S1":
                    s1_wins += 1
                else:
                    p1_wins += 1
    p = sign_test(p1_wins, s1_wins)
    print(f"overall preference (unblinded): P1 preferred {p1_wins}, S1 preferred {s1_wins}, ties {ties}; "
          f"sign test (ties excluded) two-sided p={p:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
