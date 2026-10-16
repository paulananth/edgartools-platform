# A second N-PORT quarter is a new revision of its records

Priority: 101, tier 2. Map: [Rebuild priorities](../map.md).

Type: task (configuration first; needs a small engine change). Status: done, merged (#1023, 2026-10-16 18:47 ET; skill line #1026, 19:28 ET); the run wiring part moved to ticket 79. Blocked by: none. Found by: 100 (An N-PORT link starts at its quarter's data set).

## Question

Each quarter's N-PORT records come out of `mdm.prepare` as revision 1 of the same subjects (one per CUSIP), so the Merge Stage refuses a second quarter ("Source native revision has contradictory publications"; ticket 100's check, 2026-10-16). How does a later quarter become a later revision of the same records, by configuration, so a Security's filed words and its links carry forward and a link keeps its first observed start?

## Checklist

- [x] Found: no feed configures a revision; `mdm.prepare` numbers every artifact revision 1, or takes the caller's `publication_key` and `revision` together, which refuses `effective_column` (`edgar_warehouse/workers/mdm_prepare.py`, `_published`). The Merge Stage refuses two bodies at one revision of one subject (`edgar_warehouse/mdm/clean/survivorship.py:47-54`). So configuration gives either quarters that stack (a revision per quarter, no effective time: links back in review for no start) or links that start at their quarter (one revision: a second quarter refused), not both 2026-10-16 18:06 ET
- [ ] ~~Configuration, and a two-quarter check~~ needs code (below)
- [x] Code (operator, 2026-10-16: "Code it (Recommended)"): `mdm.prepare` lets a caller that states `publication_key` and `revision` also state the publication's `effective_at` (branch `claude/prepare-stated-time`; 373 tests that use it pass) 2026-10-16 18:15 ET
- [x] Two-quarter check (scratch checkout of #1022 with this change, three invented holdings, the real chain and the Merge Stage on Docker): the second quarter applies (no revision conflict), but **the link's observed start moves to the second quarter** (2026-09-30, not 2026-06-30). Cause: survivorship keeps the newest revision only, and the link's observed start is taken from that revision's time (`edgar_warehouse/mdm/clean/survivorship.py`, `relationships.py` around 249-262); an earlier sighting is lost. Found by the Spec review 2026-10-16 18:15 ET
- [x] A link keeps its first observed start across revisions (operator: "option 1", "dont over engineer"): the Merge Stage keeps the earlier observed start its stored link holds (`relationships.keep_first_observed`); test fails without it; 1,209 MDM and integration tests pass; PR #1023 2026-10-16 18:28 ET
- [x] The data-platform skill lists `publication_key`, `revision` and `effective_at` after Codex's #1021 merges (same file; patch kept): #1026, each line checked against `mdm_prepare.py`, merged by the operator 2026-10-16 19:28 ET
- [x] Two N-PORT quarters through the real chain and the Merge Stage (`test_a_later_quarter_keeps_the_first_start`): the second quarter, a later revision with its own time, applies; the link keeps the first quarter's observed start; `last_seen` moves; fails without the Merge Stage change (#1023) 2026-10-16 18:29 ET
- [ ] ~~The N-PORT run wiring passes each quarter as its revision and time~~ deferred to 79: no platform command builds the N-PORT run yet; its run wiring part carries `publication_key`, `revision` and `effective_at`
- [x] PR #1023, CI green, merge on the operator's word: six checks green, merged on "merge one by one" 2026-10-16 18:47 ET
- [x] Learning → skill: data-platform, `mdm.prepare`'s three keys (#1026); data-onboarding's "configuration first" already covered the lesson (#1018) (2026-10-16 19:31 ET)
