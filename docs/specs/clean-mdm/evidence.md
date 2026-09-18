# Clean MDM evidence report

Date: 2026-09-18
Status: policy gate resolved; local foundation and shared merge core implemented.
Source integrations and hosted qualification/cutover remain incomplete.

## Completed investigation

- Recorded acceptance of Q1–Q16 and the explicit three-database local layout.
- Installed real migrations 023/025/026 in local `mdm` and the immutable journal
  mirror migration 024 in local `change_ledger`. Existing legacy counts stayed
  unchanged: 10 entities, 0 source references, 0 relationship instances. No
  synthetic fixture was loaded into those persistent databases.
- New acceptance suite: **30 PostgreSQL integration tests pass**, together with
  **86 existing API/publication tests (116 passed, 0 skipped in 52.35 seconds)** on disposable
  PostgreSQL 16.15. Tests exercise restricted runtime roles, atomic rollback,
  duplicate/reordered evidence, concurrent generation/checkpoint fencing,
  idempotent export/graph delivery, expired publisher fencing, shared roles,
  clear/retract/unknown time, authority conflicts, aliases, dependent reversal,
  typed relationships, hierarchy cycles, and a real three-database mirror plus
  Bookkeeping reconciliation. Synthetic fixtures are not calibration evidence.
- Command-level tests exercise the existing argparse entry points with all
  three databases: bounded resume, ordered manifest stages, journal/export/graph
  delivery and nonzero incomplete reconciliation. Fresh rebuilds vary input
  order and batch size; oversized closure rejection leaves no committed effects.
- Local review corrected arrival-dependent quarantine values, retirement review
  closure, stale Bookkeeping success, atomic-file hash/read consistency and
  mirror role checks. Both independent review agents failed on a service usage
  limit; their reviews are **not** recorded as completed.
- Added bounded reversal preview with complete rollback, immutable invocation
  attempts, role-field unknown/retraction provenance, temporal accounting-parent
  corrections, and required receipts for review resolutions in later batches.
- Opt-in authenticated v2 API tests verify shared identities, role provenance,
  aliases, historical generations and stable paginated reads. The existing API
  remains on its retained legacy contract. The installed `mdm` dependency extra
  is required for API acceptance; a run without it failed on missing FastAPI
  and was rerun with the locked extra rather than skipping those tests.
- Checked local application schema access and Bookkeeping write permissions;
  the installed console command `mdm counts --model clean` succeeded. Clean
  master batches remain zero and legacy table counts remain unchanged.
- `ruff check` passes for the new core and integration suite. The complete
  current entity-pipeline/API/hosted-consumer surface is not yet qualified.
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
- Document validation after vendor research: all 39 relative links across 15 Markdown documents
  resolved; `git diff --check` and staged whitespace validation passed.
- Fixed an independent pre-existing PostgreSQL test-fixture migration gap in
  commit `b3d94d9d`; production code and schema were not changed.
- Completed primary-source research for Matrix IDM/Rimes, Informatica,
  Ataccama and Profisee. Revised the policy interview and draft, withdrawing
  unsupported numeric thresholds and the blanket smallest-seed survivor rule.
  Research findings are not policy approval; no vendor runtime was tested.

## Matching calibration prerequisite

Calibration prerequisite check on 2026-09-18 found a frozen 1,000-company
GLEIF research cohort and 883 adjudicated candidate pairs (316 same, 480
different, 87 unresolved) in
`.scratch/gleif-company-augmentation/research/02-reviewed-candidates.jsonl`
and `02-decisions.jsonl`. Reviewer labels are from Codex agents; no documented
independent reference truth and held-out protocol was found. The existing
`02-identity-results.md` disclaims population inference and prohibits unattended
linking from its heuristic tiers. These are development examples, not proof of
the newly accepted precision target. The manifest's referenced raw GLEIF ZIP
is absent from this worktree. Matcher, issuer, ADV and reconciliation unit
fixtures are synthetic; no qualifying per-kind/rule-family corpus was found.
Versioned independent labels, representative sampling and held-out validation
remain necessary before numeric matching cutoffs can be accepted.

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
| Merge policy gate | Resolved | Q1–Q16 accepted; unqualified automatic rules disabled |
| Detailed migrations, schemas and adapter policies | Foundation installed locally | Complete concrete source adapter contracts and source integration |
| PostgreSQL 16 core | 30 integration tests pass | Complete source disposition/large-component acceptance and independent review; automatic matching remains unqualified |
| Native entity/profile/relationship pipelines | Not implemented | Every current writer routed through Merge Stage and downstream contracts verified |
| API/export/graph migration | Opt-in v2 reads tested; local envelope delivery only | Hosted consumers, crosswalks and complete compatibility/completeness evidence |
| Snowflake Postgres qualification | Not run | Same migrations/tests on isolated target with effective-role evidence |
| Rebuild/catch-up/cutover/rollback | Not run | Pinned approved inputs, live downstream reconciliation, rehearsal and release decision |

Local migration and test results above do not claim live AWS/Snowflake state,
production parity or deployment readiness.

[Current machine-readable acceptance evidence](../../../.scratch/clean-mdm/core-acceptance.json)
records the exact command, file hashes, migration checksums and test counts;
[JUnit results](../../../.scratch/clean-mdm/core-acceptance.xml) retain individual
test outcomes. [Local operations](local-operations.md) documents the implemented
commands and explicitly distinguishes local artifact delivery from hosted
export/graph qualification.
