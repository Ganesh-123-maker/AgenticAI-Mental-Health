# Research evaluation evidence — red-team detector scoring

Two evidence files, committed byte-for-byte. Verify with:

```powershell
Get-FileHash <path>\eval_heldout_main17fa077a.json -Algorithm SHA256
Get-FileHash <path>\probe_40_result.json -Algorithm SHA256
```

## `eval_heldout_main17fa077a.json`

- **SHA-256:** `00295b12bbc7be96bc42f07c7bbb1f3d61a00694b345892840d370a0c58f0900`
- **What:** Re-evaluation of held-out v1 (`data/benchmark/redteam_heldout/`,
  180 cases, 91 risk / 89 no-risk) against the detector at main
  `17fa077a`, using the repo's parameterized scorer
  (`scripts/eval_redteam_heldout.py --detector-commit 17fa077a`).
- **Result:** recall **29/91 = 0.319 (95% CI 0.232–0.420)**, false-alarm
  **21/89 = 0.236 (95% CI 0.160–0.334)**. Per-case records recompute to
  the summary exactly, all nine categories matching.
- **Turn-level severities:** 190 LOW, 48 HIGH, 2 MODERATE (240 turns).
- **Caveats:** This is a post-hoc re-evaluation, not fresh validation —
  held-out v1 is a validation set used once for diagnosis (Part B,
  frozen `630386f`); category-level Part B results were known before
  PRs #12 and #16. Labels are agent-authored; human verification
  pending. The Part B record
  (`data/benchmark/redteam_heldout/results_risk_agent.json`) is
  untouched by this file.

## `probe_40_result.json`

- **SHA-256:** `d2edcf4880c74021939fca59233e1e01ece93a5ea7f6c6485ab31d79e6525072`
- **What:** Scoring of the 40-case plain/moderate probe
  (`data/benchmark/redteam/plain_moderate_probe_40.json`: 12
  plans/means, 12 typos/slang, 16 moderate) against the detector at
  main `17fa077a`, `RiskAgent` alone.
- **Result:** recall **6/40 = 0.150 (95% CI 0.071–0.291)** — plans/means
  2/12, typos/slang 3/12, moderate 1/16. Per-case recount matches.
- **Turn-level severities:** 34 LOW, 6 HIGH, 0 MODERATE.
- **Caveats:** All 40 cases are agent-labeled positives with no
  negatives (no false-alarm rate); moderate-category labels await a
  human policy decision. This measures the detector component, not the
  user's end-to-end experience. Do not tune on this probe without a
  separate decision.
