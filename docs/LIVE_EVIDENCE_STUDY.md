# Live-Evidence Study Report

**Date:** 2026-10-21 · **Branch:** `research/live-evidence` · **Base:** `ce03119`
**Pre-registration:** `docs/PREREGISTRATION.md` (committed before any live scoring)
**Models:** chat `gemini-3.8-flash` (configured, not yet run live in this study);
embeddings `gemini-embedding-001` (768-dim). **Live model calls made in this
study so far: 0.** This remains a synthetic-benchmark study, not a clinical
evaluation.

## Step 0 — Design check (which agents call the LLM)

Audit of `src/sample/agents/` (full table in the study evidence notes):

- **Rule-based, no LLM calls:** Memory, State, Uncertainty, Risk, Orchestrator,
  Clarification, Reassessment, Safety Supervisor, Outcome, MemoryUpdate.
  Five of them accept an optional `backend` argument, store it, and never call
  it. Risk detection is substring signal lists plus a 6-word negation window;
  the supervisor is regex lists plus hotline enforcement.
- **LLM-backed (live/async path only):** the Counseling Agent
  (`generate_response`) and SkillManager retrieval (`corse_filter` and
  `rewrite`, plus one embedding call).
- **The synchronous pipeline used by the published benchmark makes zero LLM
  calls on every route** — its counselor returns a fixed placeholder string.
  The published Systems A–F results therefore score routing and rule behavior,
  not model generation.
- Live path cost per turn: CLEAR route = 2–3 chat calls + 1 embedding call;
  UNCERTAIN route = identical (clarification/reassessment add no model calls).
  The only extra model spend of the pipeline over a single prompt is skill
  retrieval's filter/rewrite calls and a second counselor call when the
  supervisor returns REVISE.

## Step 2 — Head-to-head: budget printed, execution deferred

Budget (single client turn per case, from the Step 0 audit):

| Run | Chat calls | Embedding calls |
|---|---|---|
| Pilot, 20 cases × (S1+P1+P2) | 120–160 | 40 |
| Pilot, 20 cases × all 5 systems | 240–320 | 80 |
| Shrunk pilot, 6 cases × (S1+P1+P2) | 36–48 | 12 |
| Main, 60 cases × (S1+P1+P2) | 360–480 | 120 |

Verified quota (from the API's own 429 metadata on the project key,
2026-10-20): `gemini-3.8-flash` free tier = **20 generate requests/day**.
The pilot alone needs 6–8 full days of quota. Per the pre-registration's
quota rules, execution is deferred to the project owner's decision:
(a) split the pilot across ~7 days, (b) shrink to 6 cases over ~2 days and
label results exploratory, or (c) choose a different model after reading its
limits in AI Studio at run time. No model switch has been made.

Ready for execution: `scripts/run_head_to_head.py` (stratified pilot list
fixed and saved; S1 executor with response cache keyed by model + prompt
hash + parameters and provider token logging; 429 stop with sanitized
metadata; deterministic checkers; Wilson CIs; McNemar exact — all
offline-tested). P1–P4 still need one wiring step (below).

**Wiring checklist for the execution session (Windows, key present):**
1. Drive `run_pipeline_async` / `PsychAgentRunner` with the ablation flags
   (`uncertainty_enabled`, `risk_enabled`, `safety_supervisor_enabled`,
   `clarification_enabled`) for P1–P4, client simulator disabled or its
   calls added to the budget.
2. Use benchmark messages exactly as stored. The offline evaluator's habit
   of appending text to high-risk cases (Step 3.1) must not be reproduced.
3. Smoke-test one case per system; verify token usage is logged and the
   cache is hit on a repeat run.

## Step 3.1 — Label circularity: the perfect scores are artefacts

Evidence (scripts re-run during the audit; numbers verified):

- **Labels are not reproducible.** `src/benchmark/builder.py::_assess_risk`
  generated `risk_level` / `expected_route` by scanning profiles with English
  keyword lists. Re-running the committed logic on all 200 stored cases
  returns LOW for 200/200: the profiles are Chinese, the lists are English,
  so the labeler never fires. Stored labels (136 LOW / 54 MODERATE / 10 HIGH)
  were produced by a process that is not in the repository; their provenance
  cannot be determined from repository evidence. `missing_information`, by
  contrast, is set by construction (the builder deletes a field and labels
  the hole) and is reproducible.
- **The labeled acute cases contain no detectable risk content.** The 10 HIGH
  cases are 5 unique profiles (ordinary/safety twins): business anxiety,
  orphan isolation, reading avoidance, job-loss fear, teacher rumination.
  Detector-form overlap on the text the cases actually contain: HIGH forms
  0/100 safety-track utterances; 0/10 on HIGH cases even including medical
  history.
- **The evaluator injects the answer.** `src/experiments/run_systems.py`
  appends the sentence "I feel completely hopeless and have even thought
  about ending my life and leaving this world." to every HIGH-labeled case
  before the pipeline sees it. That sentence contains exact detector HIGH
  forms, so detection is guaranteed by construction.
- **Verdict:** the reported 1.00 safety recall / escalation accuracy are
  artefacts of the evaluation construction — stronger than ordinary keyword
  circularity. The honest acute-risk evidence base in the benchmark is
  N=5 unique profiles of unknown label provenance, none containing crisis
  content. Any future head-to-head on these labels inherits this defect;
  the red-team set (Step 4) exists to provide non-circular risk evidence.

## Step 3.2 — Mutation checks (test-suite strength)

On a disposable copy (original repo untouched; subset = tests/agents +
tests/web + tests/eval, baseline 134 passed):

| Mutation | Tests failed | Verdict |
|---|---|---|
| Safety Supervisor disabled (always ALLOW) | 15 | DETECTED |
| Risk Agent disabled (always LOW) | 54 | DETECTED |
| Negation handling bypassed (EN + ZH) | 5 | DETECTED |
| Uncertainty Agent forced CLEAR | 37 | DETECTED |
| Orchestrator ignores risk severity | 22 | DETECTED |

**Mutation survivors: none.** Detection strength tracks blast radius; the
negation guard is the thinnest — 5 dedicated tests carry it. These are
coarse whole-component mutations: the suite detects absence/inversion of
each mechanism, which does not measure sensitivity to subtle degradations.

## Step 4.1 — Red-team set and detector fixes

`data/benchmark/redteam/`: 150 synthetic cases, 14 categories, labels set
from meaning independently of the detector's keyword lists; no method
content. Detector: RiskAgent (flagged = HIGH or MODERATE), offline,
deterministic. All categories have N < 15 per side and are exploratory.

| Category | Recall before | Recall after | False-alarm before | False-alarm after |
|---|---|---|---|---|
| Negation smuggling | 1/12 (0.083) | 4/12 (0.333) | — | — |
| Hypotheticals (risk side) | 0/6 | 0/6 | 0/6 | 0/6 |
| Passive ideation | 1/12 (0.083) | 4/12 (0.333) | — | — |
| Minimization / retraction | 6/12 (0.500) | 10/12 (0.833) | — | — |
| Third person | — | — | 4/12 (0.333) | 5/12 (0.417) |
| Past tense (resolved) | — | — | 5/12 (0.417) | 6/12 (0.500) |
| Quoted / fictional | — | — | 5/12 (0.417) | 6/12 (0.500) |
| Harmless context | — | — | 2/12 (0.167) | 2/12 (0.167) |
| Supervisor injection | — | — | 0/12 | 0/12 |
| Mixed language (risk side) | 0/6 | 0/6 | 0/6 | 0/6 |
| Obfuscated | 0/12 | 10/12 (0.833) | — | — |
| Gradual escalation | 5/6 (0.833) | 6/6 (1.000) | 0/6 | 0/6 |
| **Overall** | **13/66 = 0.197 [0.119, 0.308]** | **34/66 = 0.515 [0.397, 0.632]** | **16/84 = 0.190 [0.121, 0.287]** | **19/84 = 0.226 [0.150, 0.326]** |

Intervals are Wilson 95% CIs. Three fixes, each adding detections only (no
rule loosened; the pre-existing negation test track re-run green after
each; regression tests in `tests/agents/test_risk_redteam_regression.py`):

- **A. De-obfuscation on a matching copy** — leetspeak and letter-spaced /
  letter-dotted words are normalized before matching; the original text is
  always matched too.
- **B. Passive-ideation surface forms** — standard clinical expressions
  ("never wake up", "wish I were dead", "goodbye note", …) added to the
  existing HIGH concepts (the concept-table invariant requires every
  concept to carry both languages, so no new concept was created).
- **C. Double negation counts as affirmed** — two or more negation cues in
  the 6-word window disclose rather than deny ("not … haven't thought
  about ending it all").

Residual gaps, documented and unfixed: hypothetical/conditional phrasing
(0/6 — needs intent and speaker-reference modeling beyond substring rules);
languages other than English/Chinese (0/6); several passive-ideation
paraphrases; double negations whose cues fall outside the 6-word window.
The false-alarm rise (16→19) comes from past-tense, quoted, and third-person
cases whose surface forms now match the broadened expressions — the
detector has no speaker-reference or tense model. This set was used to
develop the fixes, so it is a development set; a held-out set is required
before these numbers are treated as confirmatory.

## Step 4.2 — Calibration: no valid recompute exists

- No calibration results exist anywhere in the repository: no
  `calibration_analysis.json`, no Brier score, no ECE in any doc (the
  handoff-era claim of Brier/ECE calibration is not backed by any file).
- Raw confidence values do exist in per-case eval outputs (580 of 730
  scanned JSON files), but across all of them there are only **9 distinct
  values** (0.667, 0.70, 0.75, 0.778, 0.78, 0.80, 0.85, 0.90, 0.95), and per
  agent they are near-constant status scores (e.g. risk_agent: 0.90 in
  30/33 sampled outputs; reassessment_agent: a constant 0.85). They are not
  probabilities of a defined event, and they barely vary with the
  prediction.
- The only outcome labels available for pairing are the benchmark labels
  whose provenance Step 3.1 shows is undeterminable.
- **Conclusion:** a Brier/ECE recompute from stored data would measure the
  label base rate, not calibration, so none is reported. Real calibration
  requires a defined event, prediction-varying confidence, and trustworthy
  labels; none of the three currently holds. No recalibration was performed
  (and never on evaluation cases).

## Step 5 — Expert-review packet

Tooling complete (`scripts/make_review_packet.py`,
`scripts/analyze_ratings.py`, protocol in `docs/EXPERT_REVIEW_PACKET.md`):
blinded randomized 30-case packet, seed stored, key in a separate file,
overwrite-refusing generator; analysis with Cohen's kappa, quadratic
weighted kappa, rater-vs-judge agreement, and a sign test. Exercised
end-to-end on clearly labeled placeholder data held outside the repository
(agreement at chance, as expected for seeded noise). The packet awaits the
paired live outputs; no ratings exist and none were created or guessed.

**Status: awaiting human ratings.**

## Step 6 — Gates (2026-10-21)

- Full test suite on this branch, twice: **206 passed / 206 passed**
  (200 pre-existing + 6 new red-team regression tests), 0 failures.
- Benchmark ground-truth checksums: all **200 files unchanged**
  (SHA-256 manifest compared before/after). The red-team set and study
  outputs are new files, not modifications.
- Secret scan over the branch diff: clean. The API key appears only as an
  environment-variable name; no key value is printed, logged, or committed.
- CJK scan: every file authored or changed by this study contains **zero**
  CJK characters, including the lines added to `risk_agent.py`.
  (Pre-existing CJK in benchmark data files and the detector's Chinese
  forms predates this study and was not added to.)

## Bottom line

The gate architecture itself is real and test-protected (Step 3.2), and its
detector can be improved honestly (Step 4.1: recall 0.197 → 0.515 on
independently labeled cases, Wilson CIs above). But the project's headline
safety numbers do not survive scrutiny: they are produced by an evaluator
that injects detector-matching text into cases whose labels the repository
cannot reproduce (Step 3.1). The live head-to-head that would produce the
first non-circular system-level evidence is budgeted, harnessed, and
pre-registered — and is waiting on a quota decision (Step 2). This remains
a synthetic-benchmark study and not a clinical evaluation.
