# Red-Team Benchmark (Synthetic)

Independently labeled synthetic cases for the risk and uncertainty detectors,
created 2026-10-21 as part of the live-evidence study (branch
`research/live-evidence`).

## Why this set exists

The main benchmark's safety labels could not be reproduced by the repository's
own labeler, and the offline evaluator injects detector-matching text into
high-risk cases before scoring (see the study report). This set was therefore
labeled **from meaning, independently of the detector's keyword lists**, so
detector performance on it is not circular.

## Label policy

`expected_risk = true` means a competent safety reviewer would want risk
handling for the speaker *now*. Third-person reports, historical and resolved
ideation, quoted/fictional framing, and idiomatic uses are labeled `false`
even when they contain risk vocabulary. All cases are synthetic. No case
contains method content, instructions, or encouragement.

## Contents

- `cases.json` — 150 cases across 14 categories (12 per main category;
  categories with N < 15 are exploratory).
- `results_risk_agent.json` — detector output from `scripts/eval_redteam.py`
  (RiskAgent, flagged = severity HIGH or MODERATE), with Wilson 95% CIs.
- Regenerate cases with `scripts/build_redteam_dataset.py`; re-evaluate with
  `scripts/eval_redteam.py`.

## Headline result (2026-10-21, after fixes A–C in the study report)

- Recall on risk-labeled cases: 34/66 = 0.515, Wilson 95% CI [0.397, 0.632].
  Before the fixes: 13/66 = 0.197 [0.119, 0.308].
- False-alarm rate on benign-labeled cases: 19/84 = 0.226 [0.150, 0.326].
  Before the fixes: 16/84 = 0.190 [0.121, 0.287].

Known residual gaps (documented, unfixed): hypothetical/conditional phrasing
(0/6), non-English/non-Chinese languages (0/6; the detector covers English and
Chinese forms only), several passive-ideation paraphrases, and double
negations whose cues fall outside the detector's 6-word window. This set was
used to develop the fixes, so it is a development set; a held-out set is
needed before treating these numbers as confirmatory.
