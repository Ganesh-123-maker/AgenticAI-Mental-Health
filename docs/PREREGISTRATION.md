# Pre-Registration: Live Head-to-Head Evaluation of Gateable Uncertainty/Risk Steps

**Registered:** 2026-10-21
**Status:** Registered before any live scoring for this study. No live head-to-head
run has been executed at the time of registration.
**Branch:** `research/live-evidence`
**Amendment rule:** This document is not edited after registration except by a
dated amendment appended at the end. Silent edits are prohibited.

## Research question

Does separating uncertainty detection and risk detection into explicit, gateable
steps reduce false-certainty and missed-risk rates compared with a single-pass
counseling LLM, and at what latency and token cost?

## Design

This is a synthetic-benchmark study. It is not a clinical evaluation.

Systems under comparison, all using the **same chat model, temperature, and
token limits**:

- **S1 — Single-prompt baseline.** One LLM prompt that receives the client
  message and produces a counseling response directly. No gates.
- **P1 — Full pipeline.** The 11-agent pipeline as implemented: rule-based
  detector/gate agents (uncertainty, risk, orchestration, clarification
  selection) plus LLM-backed counseling and related generation steps.
- **P2 — Pipeline without the Safety Supervisor.** P1 with the downstream
  safety gate removed.
- **P3 — Pipeline without the Uncertainty Agent** (added only if budget allows).
- **P4 — Pipeline without the Risk Agent** (added only if budget allows).

The comparison is deliberately asymmetric in mechanism and symmetric in model:
S1 is a single LLM pass; P1–P4 are rule gates plus an LLM counselor. The study
measures the effect of the gate architecture, not of a model change. A design
audit (which agents call the LLM, which are rule-based) is recorded in the
study report before results are interpreted.

## Hypotheses

- **H1 (false certainty).** P1 has a lower false-certainty rate than S1 on
  cases whose ground truth requires clarification or risk handling.
- **H2 (missed risk).** P1 has a lower missed-risk rate than S1 on cases whose
  ground truth carries risk.
- **H3 (cost).** P1 uses more tokens and has higher latency per turn than S1.
  The study reports the reliability gain per 1,000 extra tokens as a
  descriptive ratio; it is not a hypothesis test.

Null and negative results are reported as-is, including a null result for the
Safety Supervisor ablation (P2 vs P1).

## Metrics

**Primary metrics** (labels from deterministic rules against ground truth, not
from an LLM judge):

- **False-certainty rate.** Proportion of cases whose ground truth requires
  clarification or risk handling, where the system instead proceeds directly
  to counseling content without clarifying or escalating.
- **Missed-risk rate.** Proportion of ground-truth risk cases where the system
  output contains no escalation or crisis handling as defined by the
  deterministic checker.

**Secondary metrics:**

- False risk-alarm rate on the negation track (benign negated mentions flagged
  as risk).
- Unnecessary-clarification rate (clarification requested on ground-truth
  clear cases).
- Routing accuracy against `expected_route` where present.
- Tokens per turn (provider-reported usage, logged per call).
- Latency per turn (wall clock).
- Reliability gain per 1,000 extra tokens: (S1 error rate − P1 error rate) /
  (extra tokens per turn / 1000), reported descriptively for each primary
  metric.

**Qualitative scales** (appropriateness etc.) may be scored by an LLM judge
only as secondary, clearly-labeled material. If a judge is used, it is a
different model from the counselor where possible, and system identity is
hidden from the judge.

## Analysis plan

- Outcomes are **paired by case** across systems.
- Primary comparisons use the **McNemar exact test** on paired binary
  outcomes.
- **Holm correction** is applied across the family of tested comparisons.
- Every proportion is reported with its **N** and a **Wilson 95% confidence
  interval**.
- Tokens and latency are reported as medians with ranges, per system, with N.
- Results are reported whichever way they fall.

## Case-selection rule

- A **20-case pilot** runs first. Pilot cost and failure rate are reported
  before any scale-up.
- The main run uses the largest case set the daily quota allows after the
  pilot, **stratified across the five modalities** (bt, cbt, het, pdt, pmt),
  and **including negation-track and acute-risk cases** by design.
- The selected case list is fixed and recorded before scoring. No case is
  dropped after seeing outputs; failures to produce output count as failures,
  not exclusions.
- All cases are synthetic. No real patient data is used at any point.

## Budget and quota rules

- The total call budget (calls per system per case, from the design audit) is
  computed and printed before any live run.
- Daily and per-minute limits are read from API error metadata / AI Studio at
  run time, never assumed.
- If the budget does not fit the day's quota, the run is split across days or
  shrunk; shrunk runs are labeled **exploratory**.
- The chat model is not switched without the project owner's decision. If the
  model changes for any result, the model is stated beside that result.
- Responses are cached by (model, prompt hash, parameters); the cache is
  enabled for all study runs, and real token usage is logged from provider
  responses.

## Blinding and integrity

- Ground-truth files are checksummed before and after the study; any change
  voids the run.
- Safety logic (including SOP-1) is not modified by this study except for
  small, general red-team fixes with regression tests, each recorded in the
  study report. No safety rule is loosened.
- No clinical claims are made from this study under any outcome.

## Amendments

(None at registration.)
