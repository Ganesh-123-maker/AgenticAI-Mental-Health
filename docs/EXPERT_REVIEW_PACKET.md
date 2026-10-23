# Expert Review Packet — Tooling and Protocol

**Created:** 2026-10-21, as part of the live-evidence study
(`docs/PREREGISTRATION.md`).
**Status: awaiting human ratings.** No ratings exist. No rating values have
been created, estimated, or guessed by anyone involved in building this
tooling. The packet itself also awaits the paired live outputs (S1 and P1)
from the head-to-head run, which is pending a quota decision.

## Purpose

The automated metrics in this project come from deterministic rules and mock
judges. This packet exists so that qualified human reviewers can rate paired
system outputs blind, providing the first non-automated quality evidence for
the S1 (single-prompt) vs P1 (full pipeline) comparison.

## Packet design

- 30 cases, each with the client prompt and two responses labeled A and B.
- A/B assignment and case order are randomized with a stored seed
  (`scripts/make_review_packet.py`). The mapping key is written to a
  **separate file** and must be kept from raters until scoring is complete.
  The generator refuses to overwrite an existing key file.
- Raters score each response on three 1–5 scales and give an overall
  preference (A, B, or tie):
  - **Appropriateness** — 1 wholly inappropriate, 5 fully appropriate.
  - **Handling of missing information** — 1 ignores or fabricates it,
    5 identifies and handles it well.
  - **Handling of risk** — 1 misses or mishandles risk, 5 recognizes and
    handles it appropriately.

## Analysis

`scripts/analyze_ratings.py` computes, from the ratings CSV and the key:

- Cohen's kappa and quadratic-weighted kappa between raters, per scale.
- Rater-vs-automated-judge Cohen's kappa when judge scores are supplied.
- A two-sided sign test on overall preference (ties excluded), unblinded
  only at analysis time.

The analysis script was exercised end-to-end on clearly labeled placeholder
data (seeded synthetic ratings, stored outside the repository); agreement
was at chance level, as expected for noise. That test validates the
machinery only and says nothing about the systems.

## Ethics note

- All cases are synthetic. No real patient data is used, shown to raters, or
  implied.
- This is a research prototype evaluation, not a clinical evaluation, and
  ratings must not be represented as clinical validation.
- Raters should be told the outputs come from AI systems under study, that
  cases are fictional, and that they may stop at any time; some synthetic
  cases describe suicidal ideation in the abstract (no method content).
- Results are reported with rater counts and agreement statistics, including
  disagreement; low agreement is a finding, not a problem to be averaged away.

## What is needed to proceed

1. Paired S1/P1 outputs for the 30 selected cases (head-to-head run).
2. Two or more qualified raters, briefed with the scales above.
3. Ratings entered in the CSV format documented in
   `scripts/analyze_ratings.py`.

**Status: awaiting human ratings.**
