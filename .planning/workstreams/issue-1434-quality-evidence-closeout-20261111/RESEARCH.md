# Issue 1434 verified-quality branch closeout research

## Decision

Do not reopen or cherry-pick PR [#1479](https://github.com/paulaananth/edgartools-platform/pull/1479). The operator closed it at draft head `f683bbcc` without merging. Its full change set is represented in later merged work, with some implementation and test cases strengthened. No product-code transplant remains. Record the disposition on a fresh closeout branch; retain the old branch and its detached worktree as history until separately cleaned up.

The decisive integration is split across PRs [#1480](https://github.com/paulaananth/edgartools-platform/pull/1480), [#1484](https://github.com/paulaananth/edgartools-platform/pull/1484), [#1495](https://github.com/paulaananth/edgartools-platform/pull/1495), [#1499](https://github.com/paulaananth/edgartools-platform/pull/1499), [#1582](https://github.com/paulaananth/edgartools-platform/pull/1582), [#1588](https://github.com/paulaananth/edgartools-platform/pull/1588), [#1599](https://github.com/paulaananth/edgartools-platform/pull/1599), and [#1601](https://github.com/paulaananth/edgartools-platform/pull/1601). Their merge commits are in current `origin/main` (`511973670a4ecaac2d03aa728793f0b51ebbc632`). Squash merges explain why the old four commits are not ancestors of main; the PR file lists and current files provide the content check.

## Path-by-path disposition

| PR #1479 path | Evidence in merged work | Disposition |
|---|---|---|
| `.scratch/openmetadata-quality-evidence/issues/01-verified-per-load-quality-evidence.md` | Added in #1480; revised in #1484 and #1495. Later quality recovery, completed-load, UI, and issue-closeout work appears in #1582, #1588, #1599, and #1601. Current main retains the updated planning history. | Already represented; do not copy the old draft. |
| `.scratch/openmetadata-quality-evidence/map.md` | Added in #1480 and updated through #1495, #1499, #1582, #1588, #1599, and #1601. | Already represented; issue 1434 is closed by the merged closeout work. |
| `edgar_warehouse/bookkeeping/clean/quality.py` | Added by #1484, then refined for recovery in #1582. | Already represented by the current implementation. |
| `edgar_warehouse/rules/catalog.py`, `edgar_warehouse/rules/cli.py`, `edgar_warehouse/silver_writer/writer.py`, `edgar_warehouse/workers/silver_land.py` | These paths are in #1484's merged file list; subsequent quality and catalog changes are in #1582, #1588, and #1601. | Already represented; do not cherry-pick the older implementation. |
| `skills/data-operations/SKILL.md` | Updated by #1484 and refined by #1588. | Already represented by current guidance. |
| `tests/integration/test_configured_bookkeeping_postgres.py` | The old branch added `test_attempt_superseded_after_admission_precheck_is_refused_atomically`. Merged #1499 added the stronger parametrized `test_attempt_superseded_after_admission_precheck_is_refused_atomically` to this same file, covering replacement still running and replacement evidence already verified. Current main contains that parametrized test. | Behavior is covered by the merged, stronger integration test; no residual test to transfer. |
| `tests/unit/test_bookkeeping_quality.py`, `tests/unit/test_rules_catalog.py`, `tests/unit/test_silver_land_quality.py`, `tests/unit/test_silver_writer.py` | Added or updated by #1484; recovery changes landed in #1582 and precision-boundary changes in #1601. | Already represented by current tests. |

## Limits and verification

- PR #1479's recorded validation was incomplete: its own body says the PostgreSQL admission-race test could not run in that worktree because the compiled `source_contract` extension was missing, and the shipped-UI observation remained open. Those gates were later handled in separate work, rather than by merging #1479.
- PR #1499's merged file list and current `tests/integration/test_configured_bookkeeping_postgres.py` confirm the supersession test is present in a stronger two-case form. Its body records a Testmon-active PostgreSQL run with 70 passed and 63 deselected.
- PR #1484's merged file list covers every source and unit-test path from #1479 except the PostgreSQL integration file; #1499 covers that integration file. PR #1480 and later planning updates cover the two `.scratch` paths.
- This note makes no claim about the live OpenMetadata instance and performs no data, catalog, or database operation.
