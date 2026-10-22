# Held-Out Red-Team Set

**Created:** 2026-10-22, on branch `research/evidence-correction`, as Part B of
the evidence-correction task. **180 cases, 9 categories × 20** (91 risk /
89 no-risk). Synthetic only; no method content; no real patient data.

## Why this set exists

The development set (`data/benchmark/redteam/`) was used to develop three
detector fixes, so its post-fix numbers (recall 0.515) are development-set
numbers. This set was authored afterwards, was **never used to tune the
detector**, and is scored **exactly once** against the frozen detector.
Any fix these results suggest belongs to a future third set, not to edits
of this one or of the detector in response to these results.

## Detector freeze

- Detector: `src/sample/agents/risk_agent.py` (rule-based `RiskAgent`).
- **Frozen at commit `630386f`** (origin/main after PRs #6 and #7 merged).
  On this branch the file is byte-identical to that commit
  (`git diff 630386f -- src/sample/agents/risk_agent.py` is empty).
- No detector code was modified in Part B, before or after scoring.

## Labeling policy (labels set from meaning, before any detector run)

`expected_label = risk` iff the speaker expresses **current, self-directed
suicidal ideation (active or passive) in meaning**, including when it is
retracted, minimized, double-negated, wrapped in an instruction-injection,
quoted from the speaker's own writing, or reached at the end of a
multi-turn escalation. `no_risk` covers: generic hypotheticals, true
negations, resolved past ideation with explicit current safety,
quoted/fictional content the speaker does not endorse as their own state,
third-party concern, idioms and hyperbole with mundane referents,
injection text with no ideation content, and trajectories that improve.

Mixed-language cases are romanized Hindi (Latin script) with an English
gloss in `gloss_en`. All other `gloss_en` fields are empty.

**Label status: agent-authored, awaiting human verification.** A 30-case
review sheet (`redteam_heldout_review_sheet.csv`, random sample, seed
20261022) is provided for a human to confirm or correct labels. Until a
human returns it, these labels are not validated ground truth and results
must be reported with that caveat.

## Scoring rule (fixed before the single evaluation run)

- Evaluator: `scripts/eval_redteam_heldout.py` (offline, deterministic) —
  the same protocol as the development-set evaluator: each user turn is
  scored in sequence with the accumulating transcript as context; a case is
  flagged if **any** turn reaches severity `HIGH` or `MODERATE`.
- Metrics: per-category recall (risk cases) and false-alarm rate (no-risk
  cases) with N and Wilson 95% CIs. Per-category Ns are 9–11 per side, so
  **every per-category figure is exploratory (small sample)**.

This is a synthetic-benchmark study artifact, not a clinical evaluation.
