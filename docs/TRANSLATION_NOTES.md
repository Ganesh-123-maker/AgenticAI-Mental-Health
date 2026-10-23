# Translation Notes — Full-Repo Chinese → English (2026-10-22/23)

Branch: `translate/all-to-english`. All commits local; owner pushes/merges.

## Directive

Owner's final form (2026-10-22): translate EVERYTHING — datasets, detector,
outputs, `.pt` store text — word-for-word Chinese→English. Nothing removed,
reformatted, restructured, or improved; no logic changes. One earlier one-time
improvement permission was used exactly once (EN detector signal additions,
see below) before the final form superseded it.

## Method

1. **Census:** 92,547 distinct CJK strings (~2.63M chars); 191,226 CJK-bearing
   lines. Areas: profiles (72,268 distinct), skills (19,190), benchmark (7,407),
   eval outputs, sample outputs, `src/sample`, tests, `prompts/` templates.
2. **Fragment substitution (waves 1–13 + punctuation tier):** 77 shards × 1,200
   strings (frequency-sorted), translated in parallel subagent waves in
   100-string chunks, applied via a growing master map (longest-first,
   JSON-safe values: no double quotes, no backslashes, no newlines).
   28 CJK/fullwidth punctuation pairs normalized to ASCII.
3. **Line surgery (residual waves 1–7):** substitution left fragments of split
   words inside mixed lines (`不堪` → `not堪`). Each distinct mixed line
   (48,745 lines, 50,380 positions) was retranslated whole and replaced
   positionally (CRLF-safe, JSON-validated). Translators worked in 100-line
   chunks with a mandatory validator (`check_resid.py`) enforcing: no CJK /
   newlines / backslashes in values, identical indentation, JSON key, quote
   count, and trailing structural punctuation (the element-separator comma
   rule — everything after the last double-quote must match the original).
4. **sample_outputs:** 34 distinct CJK lines (716 positions) — old Chinese
   counselor-prompt snapshots + residual fragments in the new English prompt —
   translated against the already-translated `prompts/` templates.
5. **`.pt` stores:** all 15 `micro_skills.pt` text fields (`skill_name`,
   `skill_description`, `when_to_use`, `trigger`) synced 1:1 by `skill_id`
   from the translated `micro_skills.json` (4,481 entries, 17,924 fields).
   Embedding lists verified byte-identical before/after on every entry.

## Glossary (binding renderings)

overwhelmed; cannot go on living; suicide; insomnia; unable to work;
panic attack; despair; no hope; unbearable. Names → pinyin (transliterated
Western names restored: Kaiden, Lindsay, White). 女→Female, 男→Male;
未提及→"Not mentioned"; 未披露→"Not disclosed".

## Detector changes

- Batch 1: `risk_agent.py` zh signal forms → English glosses, negation cues →
  English, clause-break regex → `[.,;!?]|but|however|although`.
- The single permitted improvement: EN detector additions restoring parity
  with ZH coverage — self_harm += "slit my wrists", "cut my wrists",
  "cutting my wrists"; insomnia += "cannot sleep", "can't sleep",
  "unable to fall asleep"; overwhelm += "overwhelmed".
- `bt_404` rendering fix: the translated `main_problem` used "hopelessness"
  (from 无望感), which matches no EN detector form; adjusted to the
  glossary term "no hope" so the translated text still trips the EN
  hopelessness signal. Translation only — the test assertion was not touched.

## Test casualties (by name)

- `tests/test_migrate_skill_embeddings.py::test_est_tokens_cjk_aware` —
  FAILS by nature: its subject is CJK token estimation; no English rendering
  can pass it. Documented, not weakened.
- `tests/agents/test_risk_multilingual.py::test_repo_chinese_distress_cases` —
  failed after substitution (renderings missed the EN detector), PASSES after
  the `bt_404` "no hope" fix above. Final suite: **205 passed, 1 failed**.

## Accepted consequences

- **v1 benchmark checksums invalidated** by dataset translation (accepted
  2026-10-22).
- **`.pt` provenance break:** store texts translated in place; vectors
  preserved but computed from the original Chinese source texts. The keyed
  Gemini stores (`micro_skills.gemini-embedding-001.768.pt`, Windows-only)
  were NOT touched and now desync from the translated JSON sources.
- **Chinese-language crisis detection ends** with the detector translation.

## Upstream data anomalies (preserved, not fixed)

- Shard 010 index 502: a source string embeds the English text
  "Output too long error. Please retry with shorter output." — an
  LLM-generation artifact in the source data, preserved verbatim.
- The garbled token "sring" in profile 104 is source content, left as-is.
- Genuine U+FFFD in source data (passed through verbatim): rshard_002 line
  70; rshard_012 lines 870/986/1072; rshard_020 line 973. U+FFFD is outside
  the CJK scan ranges, so the zero-scan does not flag them.
- All other translator "garbled character" claims were terminal
  font-rendering artifacts; codepoint inspection showed intact data
  (including rshard_039 lines 1045/1056, misclaimed as literal U+FFFD).

## Campaign incidents

- Wave-1 trailing-comma incident: translators systematically added/dropped
  trailing element-separator commas (382 values); first apply broke 86 JSON
  files. Recovered via the precise tail rule (everything after the last
  double-quote must match the original); `check_resid.py` upgraded to
  enforce it; tree reverted and re-applied cleanly.
- Indent-slip repair: strengthened the validator to enforce leading-
  whitespace equality on ALL lines; found and fixed 122 slips.
- CRLF bug in `apply_resid.py` caught BEFORE any apply (would have doubled
  `\r` on replaced lines); fixed to normalize on read.
- Wave-10 concurrency: a cron run and the main turn applied concurrently;
  commit message amended to truthful text; `stage.lock` convention added
  (lock <40 min old → another runner is mid-apply; do not apply/commit).
- Wave-11: background apply killed by a runtime restart after pytest;
  recovered via lock removal + idempotent re-apply.
- pytest-env losses (×3): VM replacements wiped the pip environment
  mid-campaign ("No module named pytest"); test stack reinstalled each time.
- rshard_017 accepted deviation: the `"Should" Statements` line follows the
  shard-025 single-quote precedent for `\"` escapes (JSON-safe by parse
  test); the checker flags exactly this one line.
- rshard_041: 22 checker backslash flags on benchmark sample-output lines
  whose ORIGINALS contain structural `\"` escapes — independently verified
  (backslash counts mirrored exactly, structure identical, parsed values
  CJK-free); accepted as a valid checker exemption.
- rshard_025: translator restored a line the campaign had dropped from
  specials handling; verified byte-identical restore.
- Cron misreport (2026-10-23 07:03 IST): a cron handoff described pre-commit
  state; state verified intact, no action taken.

## Verification (final)

- Broad CJK scan (U+3400–9FFF, U+3000–303F, U+FF00–FFEF; excl. `.git`,
  `node_modules`): **0 lines** repo-wide, including `sample_outputs`.
- Full suite: 205 passed, 1 failed (the documented CJK-token casualty).
- All JSON files parse; CRLF preserved (verified against base counts).
- `.pt` payloads: 0 CJK strings; embeddings byte-identical before/after.
