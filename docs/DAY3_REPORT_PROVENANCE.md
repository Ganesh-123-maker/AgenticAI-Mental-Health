# Day 3 report provenance (2026-11-02)

The final project report rewrite lives OUTSIDE this repository, in
`~/workspace/report/`:

- `ProjectReport.docx` (464,032 bytes, 478 paragraphs, 23 tables, 2 figures)
- `ProjectReport.pdf` (90 pages, LibreOffice conversion of the docx)
- `CLAIMS_LEDGER.md` (private; NOT part of the submission; Day 3 section
  appended 2026-11-02)

The October 24 report files are preserved in the same folder as
`ProjectReport-2026-10-24.docx` and `ProjectReport-2026-10-24.pdf`.

## What this report reflects

- Base: main at `c3a6a19802717432ca488d310a60822dab99abd8`.
- Corrected docs: `final/docs` at `652faaf6`.
- English runtime configs: `final/fixes` at `4d2a4342`.
- Day 2 detector state: `final/safety` at `32bfaa90` (pending merge).
- This branch (`final/report`) records provenance only; it contains no
  report files and no code changes.

## Verified Day 3 numbers (no mismatch with the claimed Day 2 result)

- Development set, `final/safety`: recall 58/68 = 0.853 [0.750, 0.918],
  false-alarm 19/84 = 0.226 [0.150, 0.326] — re-run from a home-disk
  worktree with `scripts/eval_redteam.py` (DEV set only).
- Probe, `final/safety`: 8/40 = 0.200 [0.105, 0.348].
- Full suite: main 252 passed; `final/safety` 276 passed (confirmed by an
  independent clean home-disk comparison; scratch temp dirs must live on
  home disk, never on the 512 MB `/tmp` tmpfs, which filled to 100% on
  2026-11-02 and caused varying suite failures).

## Deliberately NOT done (Day 3)

- Held-out set NOT re-measured (Day 5 only, exactly once, with the final
  detector, after all branches merge). The report quotes held-out Part B
  ONLY (frozen detector `630386f`: recall 29/91 = 0.319, false-alarm
  19/89 = 0.213) with the slot wording:
  "TO UPDATE DAY 5: held-out re-measurement with the final detector".
- No detector tuning, no code changes, no merge, no push to main, no PR,
  no force-push, no history rewrite, no branch or file deletion.

## Reproducing the report build

Builder and figures: `~/workspace/day3-report-build/` (`build_report.py`,
`make_figs.py`, `fig_architecture.png`, `fig_results.png`,
`contents_map.json`). Build with `python3 build_report.py`, convert with
LibreOffice headless, extract heading pages with `heading_pages.py`,
rebuild with the contents map, reconvert. Full commands are in the
report's Appendix C.
