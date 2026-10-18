# Test, check and Preview for onboarding

Priority: 12, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/mastering-to-done/issues/09-test-check-and-preview-for-onboarding.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: grilling (HITL)
Status: resolved (2026-10-18): build `rules test` first and fold the rest into it; the build is ticket 14
Blocked by: 04

## Question

These are the Data Onboarding gaps found on Person feed 1 (`platform-validation/issues/05c-data-onboarding-skill-gaps.md`, 16 open items), plus rules skill 15 (`rules test`):
- `rules check --sample`;
- Preview;
- `rules save` printing the digest;
- `rules measure`;
- `rules test`.

Which of them get built before the next feed is onboarded, and in what order? The GLEIF parent approvals went ahead on hand-built test runs; `rules test` closes that gap.

## Answer

Operator, 2026-10-18: "rules test first, fold the rest (Recommended)" (2026-10-18 14:00 ET):
- `rules test` is built first (ticket 14). It covers the dry run (`rules check --sample` is `rules test --sample`), Preview (a run into a disposable MDM) and the digest (the test run names the version's digest and its input manifest).
- `rules profile` is dropped: the data-profiling skill profiles a source.
- `rules measure` waits until a measured matching rule needs it.
