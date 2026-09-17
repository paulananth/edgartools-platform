# Clean MDM evidence report

Date: 2026-09-17
Status: design gate pending; no Clean MDM runtime implementation or deployment.

## Completed investigation

- Fetched `origin/main` and inspected
  `b1babd8bbd0e04044fcacbbab822d480c97c01bc`.
- Created isolated `codex/clean-mdm` branch and sibling worktree. The primary
  checkout's untracked deployment backup and active-workstream pointer were
  preserved.
- Read accepted domain/source/run/archive decisions, existing pipeline and
  source inventories, and current code/history. Current-code findings are in
  the [inventory](pipeline-inventory.md) and [GoF review](design-review.md).
- Prepared domain, source, merge, recovery, acceptance and cutover proposals.
  No pending recommendation is recorded as user-accepted.
- Installed locked dependencies using `uv sync --frozen --extra s3 --extra
  mdm-runtime`; pulled PostgreSQL 16 into Colima. Verified binary version
  16.15 and recorded the image digest in the baseline evidence below.
- Document validation: all 26 relative links across 11 new Markdown documents
  resolved; `git diff --check` and staged whitespace validation passed.
- Fixed an independent pre-existing PostgreSQL test-fixture migration gap in
  commit `b3d94d9d`; production code and schema were not changed.

## Existing PostgreSQL baseline

Command: `uv run --frozen --extra s3 --extra mdm-runtime pytest
tests/integration/test_acquisition_ledger_postgres.py -q --tb=short`.

Initial result: 4 passed, 6 failed, 0 skipped. The fixture installed migrations
013 and 017 but omitted 018; current ORM writes require its `captured_etag`
and `captured_last_modified` columns. Adding 018 exposed a second fixture
ordering problem: privileged 013 reruns restore an obsolete seven-argument
`finalize_source_fetch` overload. Reapplying 018 after those reruns matches the
runtime's ordering and removes ambiguous function dispatch.

Final result: **10 passed, 0 failed, 0 skipped in 12.44 seconds**, on disposable
PostgreSQL 16.15 using real migration SQL and restricted application-role
connections. Fixtures stopped their temporary containers afterward.
[Machine-readable baseline evidence](../../../.scratch/clean-mdm/postgres-baseline-evidence.json)
records both outcomes, the exact tests, image digest and test-file hash.

These tests cover the existing acquisition ledger, permissions, fencing,
source revisions and processing settlement. They do not prove the proposed
Clean MDM identities, Merge Stage, consumer contracts or reversal behavior.

## Evidence still required

| Delivery | State | Required next evidence |
| --- | --- | --- |
| Merge policy gate | Pending | Actual user decision on the linked Wayfinder frontier |
| Detailed migrations, schemas and adapter policies | Not implemented | Gate resolution, reviewed physical contract and implementation tickets |
| PostgreSQL 16 core | Not run | Real migrations, restricted-role execution, fixture permutations and crash/retry suite with zero prerequisite skips |
| Entity/profile/relationship integration | Not implemented | Every current writer routed through Merge Stage and downstream contracts verified |
| API/export/graph migration | Not implemented | Versioned contracts, consumer inventory and compatibility/completeness evidence |
| Snowflake Postgres qualification | Not run | Same migrations/tests on isolated target with effective-role evidence |
| Rebuild/catch-up/cutover/rollback | Not run | Pinned approved inputs, live downstream reconciliation, rehearsal and release decision |

No Clean MDM migration success, live AWS/Snowflake state, production parity,
or deployment readiness is claimed by these documents.
