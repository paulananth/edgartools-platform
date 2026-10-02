# Test reduction implementation evidence

## Retired caller audit

The executable CLI calls `_runtime_parser()`, which exposes only Rules,
Bookkeeping, Change Journal, MDM, and Snowflake environment resolution.
`acquisition_command_registry` has no registrations. `command_router.run_command`
and `warehouse_orchestrator.run_command` reject the four retired acquisition
routes. Source definitions and historical deployment script helpers remain in
the repository, but these cannot be reached through the executable CLI.

The 45 exact removed node IDs are in [removed-nodeids.txt](removed-nodeids.txt):

| Removed surface | Cases | Retained boundary evidence |
| --- | ---: | --- |
| ADV bulk fetch caller | 18 | `tests/architecture/test_company_only_acquisition.py::test_retired_feeds_have_no_source_declaration_or_command` rejects `fetch-adv-bulk` through `main()` and both routers. Shared ADV ingest/parser tests remain. |
| Firm Roster fetch caller | 18 | Same architecture node rejects `fetch-firm-roster`. Shared Firm Roster parser and MDM mapping tests remain. |
| ADV bronze discovery caller | 4 | Same architecture node rejects `parse-adv-bronze` and `drive-adv-bulk-dataset-discovery`. |
| Bronze batch seeding caller | 4 | Same architecture node rejects `seed-bronze-batches`. |
| Stale deployed-command assertion | 1 | Same architecture node rejects `fetch-adv-bulk` through executable `main()`. |

The architecture node is a route replacement, not a claim that the removed
caller behavior is still supported. No duplicate-equivalence claim is made.

## Large-file inventory

[reviewed-nodeids.txt](reviewed-nodeids.txt) records all 367 collected node IDs:
114 release-evidence cases, 91 MDM activation cases, 86 proxy parser cases,
and 76 Rules-file cases. I retained all of them after reviewing their branch
and failure-mode matrices: release cases cover separate malformed evidence,
identity, attestation, approval, and secret boundaries; MDM cases cover
separate rule shape, proof threshold, version, and approval failures; proxy
cases cover different text/footnote patterns; Rules files cover scalar
coercion, aliases/tags, duplicate keys, and Unicode. No case was removed on
an unproven equivalence, so no deliberate fault is claimed for these files.

## Slow-path investigation

- Local affected Application, architecture, and submission-phase run: 699
  passed. Its 355-second outlier was a parser dependency import on macOS;
  these local times are not CI timing evidence.
- Local Company PostgreSQL 16 acceptance: 2 passed, including main/page
  pagination and MDM publication. Measured setup was 30.08 seconds and the
  end-to-end Company case was 71.17 seconds. Its fixture creates databases,
  migrations, and restricted roles once per module.
- Local MDM API probe: 53 passed in 35.14 seconds. The slowest first setup
  was 5.24 seconds; later per-case setups were below one second. Each case
  creates an isolated in-memory schema and a real-auth TestClient.
- The two 2.1-second lease-expiry waits are inside transactions with deferred
  commit-time checks. Administrator updates from another connection would
  block on the transaction's row locks; changing the protected value inside
  the transaction would test a different condition. They remain until a
  deterministic clock or equivalent transaction-safe seam can preserve the
  same rollback and stale-lease assertions. The 3.2-second real heartbeat
  timing case remains.

## Coverage retained

The CI gate still runs Unit, Architecture, MDM, Application, and PostgreSQL
integration tests plus shell lint. The PostgreSQL job provisions image
`postgres:16-alpine` and restricted roles; prerequisites fail instead of
skipping. Company pagination, Journal outage and recovery, lease fencing,
MDM publication, and release security remain covered by their existing tests.

Against `main` at `f71c6c1e`, collected cases changed from 3,579 to 3,534:
Unit 1,455 -> 1,454; Application 339 -> 295; Architecture 370, MDM 1,114,
and PostgreSQL integration 301 (300 passed, 1 expected failure) stayed the
same. The MDM count is one higher than the prior plan's 1,113 because `main`
advanced with Company mastering ticket 26 while this work was in progress.

## CI layout experiment

The separate pilot moves Application pytest into the Unit job as its own
step. Keep it only if five runs of each layout on otherwise identical code
show at least 10% lower median gate time and no worse observed maximum.
Measure runner queue separately from job execution. Results will be added
after the paired runs.

Five unchanged-layout attempts of [PR #760](https://github.com/paulananth/edgartools-platform/actions/runs/36658661466),
all on head `289c632c`, passed:

| Attempt | Gate seconds | Integration execution seconds | Integration queue seconds | Application execution seconds | Application queue seconds |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 150 | 142 | 2 | 20 | 2 |
| 2 | 129 | 120 | 2 | 20 | 2 |
| 3 | 160 | 149 | 2 | 22 | 2 |
| 4 | 160 | 151 | 4 | 19 | 2 |
| 5 | 141 | 133 | 2 | 18 | 2 |

Baseline median is 150 seconds; observed maximum is 160 seconds. The
integration job is the gate's long pole in every attempt. Queue times were
small, so the Application job did not measurably delay its start in this
sample. The pilot branch changes only `.github/workflows/ci.yml` relative to
the cleanup branch; the test code and `main` merge base are the same.

The immediate `main` run at `f71c6c1e` also took 150 seconds to the gate
([run 36658565116](https://github.com/paulananth/edgartools-platform/actions/runs/36658565116)).
That single pre-deletion run and the five post-deletion attempts do not show
a gate-time reduction from deleting the 45 cases. Per the stopping rule, no
active duplicate cases were deleted for speed.

Five pilot attempts of [PR #761](https://github.com/paulananth/edgartools-platform/actions/runs/36659798413),
all on head `0ea0222f`, also passed all suites and the gate:

| Attempt | Gate seconds | Integration execution seconds | Integration queue seconds | Combined Unit execution seconds | Combined Unit queue seconds |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 150 | 142 | 2 | 70 | 2 |
| 2 | 157 | 149 | 2 | 65 | 2 |
| 3 | 167 | 158 | 2 | 70 | 2 |
| 4 | 157 | 149 | 2 | 71 | 2 |
| 5 | 133 | 123 | 3 | 65 | 2 |

Pilot median is 157 seconds (4.7% slower than baseline); observed maximum
is 167 seconds (7 seconds worse). Runner queues stayed at 2-4 seconds. The
sample does not establish that the layout caused PostgreSQL execution to
vary, but it provides no evidence of the required 10% gate improvement and
fails the no-worse-maximum rule. Draft PR #761 was closed without merging;
the unchanged four-job-plus-shell-lint CI layout remains in PR #760.
