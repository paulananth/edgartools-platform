# Mastering qualification: Claude continuation of draft PR #780

Source: Codex draft [PR #780](https://github.com/paulananth/edgartools-platform/pull/780),
branch `codex/mastering-rebuild-20261001`, head `744cba55` (verified 2026-10-02 09:00 ET),
handoff `.planning/workstreams/mastering-rebuild/HANDOFF-to-claude-20261002.md`.
Branch `claude/mastering-qualification-20261002`, own worktree.
Status: closed 2026-10-02 10:02 ET, except the Codex memory note, which is handed back to Codex. The operator forwarded the handoff on 2026-10-02.

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
- [x] Review: Standards, Spec, GoF (three parallel reviewers over `git diff origin/main...HEAD`). 2026-10-02 09:55 ET
  - [x] GoF: leave the code as is; no change has repeated along any one line. Noted only: the skip rule in the runner is keyed by suite name.
  - [x] Standards:
    - Fixed: import order, a lambda assigned to a name, and an unclear `[1]` tuple index.
    - Not taken: the two "hard" findings, that the runner can't pass the known-failure list or the 16-minute integration run. Both rest on old CLAUDE.md figures; today's CI integration job had 290 passed, with only this test failing, in 137 s.
    - Docs and `TODOS.md` still name the deleted loaders; that is history, left.
  - [x] Spec:
    - The refusals now assert SQLSTATE 42501, not any database error.
    - Publication read-back now asserts files on disk for each consumer.
    - The calculated ultimate-parent link's ends are now checked.
    - Codex's five docs carry a "superseded in part" note, and the consolidation tick in its TICKET is struck through as deferred.
    - Locally: 2 passed in 31 s, no leftover container.
  - [x] The CLAUDE.md/AGENTS.md rewrite was a finding for the operator. Operator, 2026-10-02: "Split it out (Recommended)". Both files are back to main's text in commit `b9e3628d`; the rewrite is now `.scratch/agent-guides/issues/01-consolidate-claude-and-agents-md.md`. 2026-10-02 09:25 ET
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
  - [x] `qualify_local_mastering.py` runs all four suites locally. It is kept as Codex wrote it. `docs/agents/mastering-operations.md` now says it is the long run, used only when it is the evidence asked for; everyday work runs the affected tests locally. 2026-10-02 09:30 ET
- [x] Fix the acceptance test so it uses a relationship the approved rules allow.
  - Two GLEIF Level 1 records (Apple, Microsoft) and one synthetic accounting-parent record go through the real `gleif_source.record_evidence` reader.
  - The GLEIF records wait for binding under the approved rules, so a steward binds each to its SEC Company.
  - The link resolves to the two canonical Company IDs, plus the calculated ultimate parent.
  - No Person link type is approved yet (platform validation 06, step 2).
  - Locally: 1 passed in 32 s, no leftover container; testmon over `tests/mdm` and `tests/unit`: 5 passed in 9 s. 2026-10-02 09:24 ET
- [x] Inventory the local databases, read-only, with nothing removed. 2026-10-02 09:33 ET
  - `rules-local-person-feed-1` (pg16-alpine, port 34212): `rules` (`rules`: 1 table). It holds tonight's GLEIF approvals. Keep.
  - `edgartools-change-journal-local-235e8eec` (pg16, port 33613):
    - `bookkeeping_clean` (`bookkeeping`: 5 tables);
    - `change_journal_clean` (`journal`: 1);
    - `rules` (`rules`: 1).

    Protected by the operator's rule.
  - `edgartools-clean-mdm-pg16` (pg16-alpine, port 5432, volume `edgartools-clean-mdm-pg16-data`):
    - `mdm`: legacy `public` (27 tables, about 7 rows) and the pre-rename `mdm_v2` (13 tables);
    - `silver`: `public` (6 tables, 3,024 rows);
    - `bookkeeping_clean`;
    - `rules`.

    Current code uses schema `mdm`, so this store cannot run today's migrations without being recreated. Recreating it is the operator's call.
  - Volumes not attached to a container: `edgartools-catalog_db-data` and `edgartools-catalog_es-data`, created 2026-09-28. The catalog stack was removed on 2026-10-01; its volumes were kept by the cleanup rule.
  - No client connections on any store.
- [x] Remove the databases that are not needed (operator, 2026-10-02: "merge, delete any db that is not needed"). 2026-10-02 10:02 ET
  - Removed:
    - `edgartools-clean-mdm-pg16` and volume `edgartools-clean-mdm-pg16-data`. It held legacy MDM test rows, an empty `mdm_v2`, 3 test Companies in an old local `silver`, and empty `rules` and `bookkeeping_clean`. Today's code cannot migrate it.
    - `edgartools-change-journal-local-235e8eec` and its volume. Its three databases had no rows.
    - The orphaned catalog volumes `edgartools-catalog_db-data` and `edgartools-catalog_es-data`.
  - Backups first, in `~/.local/share/edgartools/db-backups-20261002/`:
    - both stores as `pg_dumpall` (52 and 7 tables);
    - both catalog volumes as tar.
  - Kept: `rules-local-person-feed-1`, with its 4 rule versions including the GLEIF parent approvals; switch-on needs them.
  - Checked with `docker ps -a` and `docker volume ls`: one container and one volume remain.
- [x] Claude memory: `project_v2_clean_mdm_is_the_priority.md` now names schema `mdm` and the `data-onboarding` and `refining-rules` skills; the operator's rebuild decision is kept. 2026-10-02 09:35 ET
- [ ] ~~Codex memory note~~ handed back to Codex: it is Codex's memory store, and Codex now has write access
- [x] Open a continuation draft PR linking #780: #781, carrying every #780 commit; code outside the edited tests is identical to `744cba55` (git diff); #780 has a comment linking #781. 2026-10-02 10:00 ET
- [x] Close #780 as superseded: #781 merged as `b34f5b06`; `git diff` shows no code difference from #780's head; #780 closed with a comment. 2026-10-02 10:01 ET
- [x] CI green on the continuation PR #781: all 5 checks passed, and the integration job ran the fresh mastering acceptance (gh pr checks). 2026-10-02 10:12 ET
