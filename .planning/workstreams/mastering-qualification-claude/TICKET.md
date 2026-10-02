# Mastering qualification: Claude continuation of draft PR #780

Source: Codex draft [PR #780](https://github.com/paulananth/edgartools-platform/pull/780),
branch `codex/mastering-rebuild-20261001`, head `744cba55` (verified 2026-10-02 09:00 ET),
handoff `.planning/workstreams/mastering-rebuild/HANDOFF-to-claude-20261002.md`.
Branch `claude/mastering-qualification-20261002`, own worktree.
Status: open. The operator forwarded the handoff on 2026-10-02.

Standing operator rules that override the handoff where they differ:
- run only the affected tests locally; CI runs everything (2026-09-29, 2026-10-01);
- remove no database or volume unless the operator names it;
- merge only on the operator's word.

## Checklist

- [x] Verify the source PR and set up the worktree: #780 is OPEN, a draft, head `744cba55`; worktree created off that head. 2026-10-02 09:00 ET
- [x] Check that the deleted modules have no callers: on origin/main, `stage_daily_index_filing_loader`, `seed_universe_loader` and `mdm.clean.securities.publish` are used only by `loaders/__init__.py` and their own deleted tests; the other hits are docs and `.scratch` notes (git grep). 2026-10-02 09:02 ET
- [x] Run the new acceptance test (once locally and once in CI). It **fails** with `Conflict: Company policy has no source priority for: fixture.secondary`. The synthetic EMPLOYED_BY link comes from a source that the approved Company rules do not list.
  - Locally: 1 failed, 4 passed in 65 s; no leftover test container.
  - CI integration job: 1 failed, 290 passed in 137 s.
  - 2026-10-02 09:03 ET
- [ ] Review: Standards, Spec, GoF
  - [ ] The CLAUDE.md/AGENTS.md rewrite is a finding for the operator.
    - CLAUDE.md shrinks to 17 lines and mentions AGENTS.md only in prose, with no `@AGENTS.md` import.
    - Dropped from always-loaded text:
      - the AWS account map;
      - the warning that dev Snowflake is decommissioned;
      - the rule never to pipe secrets to head or cat;
      - the testmon commands;
      - the Snowflake and Postgres lessons;
      - known open items;
      - 5-whys;
      - the BIGINT rule.
  - [ ] `qualify_local_mastering.py` runs all four suites locally. This conflicts with the operator's affected-tests rule. CI already runs the full integration suite in about 2 minutes.
- [ ] Fix the acceptance test so it uses a relationship the approved rules allow
- [ ] Inventory the local databases (containers, databases, schemas, connections), report only, and remove nothing without the operator's named target
- [ ] Claude memory: fix the `mdm_v2` and single-rules-skill references in `project_v2_clean_mdm_is_the_priority.md`
- [ ] ~~Codex memory note~~ handed back to Codex: it is Codex's memory store, and Codex now has write access
- [ ] Open a continuation draft PR linking #780. Close #780 as superseded only after its full diff is confirmed carried over
- [ ] CI green on the continuation PR
