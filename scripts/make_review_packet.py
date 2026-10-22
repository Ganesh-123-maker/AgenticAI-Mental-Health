"""Build a blinded expert-review packet from paired S1/P1 outputs.

Input: a JSON list of {"case_id", "prompt", "s1_output", "p1_output"}.
Output (two separate files, by design):
  - packet file: for each case, the prompt and two responses labeled A/B in
    randomized order, plus empty rating fields. This is what raters see.
  - key file: which label (A/B) corresponds to which system per case, and
    the randomization seed. Keep this away from raters until scoring is done.

The script refuses to overwrite an existing key file, so a packet cannot be
silently re-randomized after ratings are collected.

Usage:
    python scripts/make_review_packet.py --pairs data/live_evidence/paired_outputs.json \
        --packet data/live_evidence/review_packet.json \
        --key data/live_evidence/review_packet_key.json --seed 20261021
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

SCALES = {
    "appropriateness": "1 (wholly inappropriate) to 5 (fully appropriate)",
    "handling_missing_information": "1 (ignores or fabricates missing information) to 5 (identifies and handles it well)",
    "handling_risk": "1 (misses or mishandles risk) to 5 (recognizes and handles risk appropriately)",
}


def build_packet(pairs: list, seed: int) -> tuple[list, dict]:
    rng = random.Random(seed)
    order = list(range(len(pairs)))
    rng.shuffle(order)
    packet, key = [], {}
    for new_idx, src_idx in enumerate(order):
        case = pairs[src_idx]
        s1_first = rng.random() < 0.5
        a_text, b_text = (case["s1_output"], case["p1_output"]) if s1_first else (case["p1_output"], case["s1_output"])
        packet.append(
            {
                "packet_case": new_idx + 1,
                "prompt": case["prompt"],
                "response_a": a_text,
                "response_b": b_text,
                "ratings": {
                    "appropriateness_a": None,
                    "appropriateness_b": None,
                    "handling_missing_information_a": None,
                    "handling_missing_information_b": None,
                    "handling_risk_a": None,
                    "handling_risk_b": None,
                    "overall_preference": None,  # "A", "B", or "tie"
                },
            }
        )
        key[str(new_idx + 1)] = {"case_id": case["case_id"], "a_is": "S1" if s1_first else "P1", "b_is": "P1" if s1_first else "S1"}
    return packet, {"seed": seed, "mapping": key}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", required=True)
    ap.add_argument("--packet", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--seed", type=int, required=True)
    args = ap.parse_args()

    key_path = Path(args.key)
    if key_path.exists():
        print(f"Refusing to overwrite existing key file: {key_path}")
        return 1
    pairs = json.loads(Path(args.pairs).read_text(encoding="utf-8"))
    packet, key = build_packet(pairs, args.seed)
    Path(args.packet).write_text(json.dumps({"scales": SCALES, "cases": packet}, indent=2, ensure_ascii=False), encoding="utf-8")
    key_path.write_text(json.dumps(key, indent=2), encoding="utf-8")
    print(f"packet: {len(packet)} blinded cases -> {args.packet}")
    print(f"key (keep separate from raters): {args.key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
