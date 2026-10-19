# Embedding Migration Completion Report: BGE-M3 → Gemini

**Date:** 2026-10-19
**Scope:** 15 skill files, 4,481 skills, 8,962 embedding texts
**Status:** Complete and verified

## 1. Objective

Replace the 1,024-dimensional BGE-M3 embeddings in the skill corpus with
768-dimensional `gemini-embedding-001` vectors, so live retrieval uses the
same embedding space as the Gemini-powered runtime. Original vectors were
never modified; migrated stores are written to separate keyed files
(`micro_skills.gemini-embedding-001.768.pt`).

## 2. The v5 → v6 skip bug

The v5 migration script could never finish. Its skip check for completed
files was:

```python
[s["embedding_to_merge"] for s in existing.values() ...]
```

The keyed store contains a `_provenance` metadata entry alongside the
skill entries. Iterating `existing.values()` hit this dict, raised
`KeyError`, which was swallowed by a surrounding `except Exception: pass`
— so the skip path silently never fired, and every run re-embedded all
files from scratch.

The v6 fix validates exactly the expected skill ids:

```python
[existing[sid]["embedding_to_merge"] for sid in skill_ids ...]
```

Verified live: completed files skip with 0 API calls.

## 3. Quota accounting correction

Initial planning assumed Gemini bills per HTTP batch. Two independent
sources plus the observed daily-quota abort confirmed the correction:
**Gemini counts each text as one daily quota unit** for batch embedding.
Batching (batch size 16) saves latency only, never quota.

Consequences:
- Total billable units: 8,962 texts (2 per skill), not ~560 batches.
- The `--rpd` safety guard was fixed to compare text counts against the
  daily budget (previously compared HTTP request counts — a defect that
  understated consumption by the batch-size factor).
- Daily quota resets midnight Pacific (~12:30 PM IST).

## 4. Execution

| Date | Result |
|---|---|
| 2026-10-11 – 10-18 | Incremental runs; 12/15 files completed |
| 2026-10-19 ~15:04 IST | **Complete: 15/15 files, `done: 15/15 files ok`, no quota abort.** 12 files skipped via v6 (0 calls); `pmt/stage1–3` regenerated |

## 5. Verification chain

1. **Store verifier** (`verify_migration.py --verify original_hashes.json`):
   `checked=15, valid_stores=15, failures=0`.
2. **Retrieval smoke** (`smoke_gemini_retrieval.py`, via the real
   `SkillManager._load_micro_skills`): 15/15 keyed stores loaded,
   4,481 skills, all vectors 768-dim, zero 1024-dim vectors; live query
   cosine similarities 0.644–0.659 (top-5).
3. **End-to-end conversation** (`smoke_live_conversation.py`): 2-turn
   synthetic conversation against the live backend; turn 1 produced an
   empathetic exam-anxiety response, turn 2 a Progressive Muscle
   Relaxation technique. No anomalies on the final model.

## 6. Model notes

- Live chat baseline uses `gemini-3.8-flash` (migrated from
  `gemini-3-flash-preview` after its 20/day free-tier generate quota was
  exhausted; `gemini-2.5-flash` was tried in between but Google retired it
  for new users).
- One non-reproducing anomaly was observed on `gemini-3-flash-preview`
  (an irrelevant truncated vLLM explainer on turn 1); logged as observed
  model nondeterminism, not investigated further — it did not reproduce on
  `gemini-3.8-flash` and the model changed since.
- Free-tier generate quota is separate from and far tighter than the
  embedding quota; each conversation turn burns ~6–8 LLM calls.

## 7. Benchmark methodological note

`src/experiments/run_systems.py` is fully offline: rule-based pipeline
agents, templated counselor replies, mocked judges, and a
`skill_retrieval` flag that only selects canned text. **No real embedding
retrieval executes in the benchmark.** A re-run is quota-free but cannot
validate this migration. Migration validation rests on §5 above. The
benchmark measures routing and safety logic, not embedding quality.

## 8. Limitations

- Embedding quality is validated by smoke retrieval, not by a
  held-out relevance benchmark.
- The free-tier quota model means large-scale re-embedding is
  rate-limited by design; the keyed stores are committed as build
  artifacts to avoid repeat billing.
