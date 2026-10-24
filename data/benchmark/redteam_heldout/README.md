# Held-Out Red-Team Set

## Status (2026-10-24 addendum — read first)

This set is a **validation set used once for diagnosis**: Part B scored it
exactly once against the detector frozen at `630386f`. It is **not** a clean
held-out set for later detectors. Category-level Part B results (notably weak
hypotheticals and mixed-language recall) were known before PRs #12 and #16,
so effort after Part B was steered by those results, even though no case text
was edited and no case was used to write a detector form. Later
re-evaluations against newer detectors (e.g. `17fa077a`) are post-hoc
comparisons, not fresh validation; any improvement claimed on this set after
Part B would be suspect, and a fresh v2 set is needed to claim
generalization. **Labels are agent-authored; human verification pending**
(30-case review sheet, unreturned). Cases and the Part B record
(`results_risk_agent.json`) are unchanged; only this note was added.

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

## Results — single evaluation run, 2026-10-22 (frozen detector, no post-hoc fixes)

| Category | Recall (k/N) | False-alarm (k/N) |
|---|---|---|
| hypotheticals | 2/11 = 0.182 [0.051, 0.477] | 2/9 = 0.222 [0.063, 0.547] |
| negation_smuggling | 2/10 = 0.200 [0.057, 0.510] | 2/10 = 0.200 [0.057, 0.510] |
| mixed_language | 0/10 = 0.000 [0.000, 0.278] | 0/10 = 0.000 [0.000, 0.278] |
| past_tense | 4/10 = 0.400 [0.168, 0.687] | 7/10 = 0.700 [0.397, 0.892] |
| quoted_fictional | 3/10 = 0.300 [0.108, 0.603] | 3/10 = 0.300 [0.108, 0.603] |
| third_person | 2/10 = 0.200 [0.057, 0.510] | 3/10 = 0.300 [0.108, 0.603] |
| minimization_retraction | 5/10 = 0.500 [0.237, 0.763] | 2/10 = 0.200 [0.057, 0.510] |
| supervisor_injection | 8/10 = 0.800 [0.490, 0.943] | 0/10 = 0.000 [0.000, 0.278] |
| gradual_escalation | 3/10 = 0.300 [0.108, 0.603] | 0/10 = 0.000 [0.000, 0.278] |
| **Overall** | **29/91 = 0.319 [0.232, 0.420]** | **19/89 = 0.213 [0.141, 0.310]** |

Wilson 95% CIs. Every per-category row is exploratory (N < 15 per side).

Reading: held-out recall (0.319) is substantially below the development
set's post-fix 0.515, confirming development-set optimism and showing the
fixes generalize narrowly — negation smuggling 0.200 (the double-negation
rule covers few of these phrasings), hypotheticals 0.182 (self-referential
ideation in conditional form is mostly missed), mixed language 0.000
(romanized Hindi is outside the detector's EN/ZH coverage). The largest
false-alarm source is resolved past-tense ideation (0.700): with no tense
model, historical disclosures flag as current. Explicit ideation stays
detectable even inside injection wrappers (0.800, false alarms 0/10).
Per-case results: `results_risk_agent.json`. No detector change was made
in response to this run.

This is a synthetic-benchmark study artifact, not a clinical evaluation.
