# Source evidence and relationship calculation modules

Type: task
Status: in progress

Spec: [combined scope](../spec.md). Base `1f1c55edc`. Implement both in one dedicated branch and PR; preserve behavior.

## Parts

- [x] Inspect live ownership, history, ADRs and GoF costs; create isolated branch and settle seams. — branch 1f1c55ed, overlap guard clean, GoF/ADRs checked (2026-10-17 19:48 ET).
- [x] Establish affected test baseline and characterize relationship temporal/history order before editing production code. — 118 passed in 46.78s, including six new temporal/history characterizations (2026-10-17 19:48 ET).
- [x] Add failing Source Extract seam test; implement one private opened view, copied evidence and bounded lazy iteration. — missing OpenedExtract failed, then 33 extraction/lookup cases and 190 affected cases passed (2026-10-17 19:52 ET).
- [x] Consolidate bounded lookup authentication; migrate source.read and Name Frequency without moving consumer policy. — one lookup implementation, no consumer private calls/synthetic manifest; 190 affected cases passed (2026-10-17 19:52 ET).
- [x] Verify metadata/lookup mutation isolation, lazy partition reads, formats, empty/multiple artifacts and all existing bounds/refusals. — new opened-extract tests plus incremental/lookup/worker suites, 190 passed in 26.66s (2026-10-17 19:52 ET).
- [x] Verify Name Frequency canonical output, wrong publication/recipe/population and late-failure no-publication behavior; retain newer cascade coverage. — canonical output/cascade tests and four new late-corruption/cancellation cases passed in the 190-case group (2026-10-17 19:52 ET).
- [x] Move stored observed-start reconciliation into relationship calculation; remove Merge Stage period sequencing while preserving scoped retrieval/filtering and temporal order. — stored keyword failed before implementation; six old-sequence characterizations pass through project; Merge Stage retains indexed retrieval/filtering (2026-10-17 19:52 ET).
- [ ] Verify hierarchy/profile/succession/derived-parent interaction, Person periods, N-PORT revisions and PostgreSQL first-start/merge/reversal/recovery cases.
- [ ] Verify runtime fingerprints, scoped types/architecture and installed full-path proof on disposable PostgreSQL.
- [ ] Review Standards, Spec and GoF independently where required and resolve findings.
- [ ] Commit/push with overlap guards, open PR and verify full CI with a bounded watcher.
- [ ] Learning → skill: assess and record relevant lesson or none.

## Verification notes

Baseline: 118 passed in 46.78s including six pre-refactor temporal characterizations. Opened-extract first test failed on missing interface; history test failed on the new stored argument. The first lookup extraction run caught an omitted codec name; corrected and all 33 cases passed.

A shared testmon SQLite cache failed its foreign-key write after 119 successful tests. No cache was deleted. All later runs use a worktree-specific file under ~/.cache/edgartools/ and testmon remains enabled. The 190-case affected run completed cleanly.

Pyright is clean for source_read, source_readings and relationships. Compared with the same 1f1c55ed source, merge and name_frequency have the same 12 pre-existing diagnostics (same messages/rules; only moved line numbers), with none added by this change.
