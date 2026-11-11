# Bookkeeping OpenMetadata Closeout Research

## Finding

Do not replay PR [#1432](https://github.com/paulananth/edgartools-platform/pull/1432) as a whole. Its main feature, a periodic external observer that discovers Bookkeeping loads, reads an aggregate snapshot, and publishes each run to OpenMetadata, is absent from current `origin/main` (`5dd4d691`). Later work provides two adjacent, narrower capabilities: explicit latest-run Pipeline status via `rules catalog status --bookkeeping-run RUN_ID` ([#1501](https://github.com/paulananth/edgartools-platform/pull/1501), documented and availability recorded by [#1507](https://github.com/paulananth/edgartools-platform/pull/1507)), and per-load quality-result publication ([#1484](https://github.com/paulananth/edgartools-platform/pull/1484), end-to-end evidence in [#1588](https://github.com/paulananth/edgartools-platform/pull/1588)). Neither implements periodic discovery/progress reporting.

Current main contains no ticket or acceptance criterion establishing the periodic observer as required. Treat it as an unimplemented, separately scoped follow-up only if an owner confirms the need; the closed branch and its dated ticket do not establish current priority. The [#1418 closeout report in PR #1635](https://github.com/paulananth/edgartools-platform/pull/1635) already states this boundary, so this report records the #1432 reconciliation without repeating that workstream’s OpenMetadata analysis.

## Branch and check evidence

PR #1432 was closed, not merged. Its retained remote head is `04c3e9c3f392b21c36b89fa9c4a7058cf51f2a42` (`Fix equal-timestamp Bookkeeping run discovery`), based on `d9e5764c`. The PR body’s statement that corrected-head CI remained required is stale: live `gh pr checks 1432` shows all 20 checks on that current head passing, including CI gate, unit/MDM, PostgreSQL integration, Rust, shell lint, Postgres/MySQL/MSSQL skill-adapter, and storage/workflow checks (run [42123394090](https://github.com/paulananth/edgartools-platform/actions/runs/42123394090)). The PR was nevertheless closed at operator request. Its reported local/manual run counts are dated Nov 5 observations, not current-state evidence.

The full branch diff from current main is 12 paths (790 insertions, 5 deletions):

| PR #1432 path | Current-main comparison |
| --- | --- |
| `.planning/workstreams/bookkeeping-openmetadata/TICKET.md` | Branch-local proposal and acceptance gates only; not present on main. |
| `edgar_warehouse/application/load_observer.py` | Absent. Main has no `observe loads` command or observer app. |
| `edgar_warehouse/bookkeeping/clean/cli.py` | Observer-facing CLI support is absent. Current CLI retains ordinary Bookkeeping controls and explicit status-related routines. |
| `edgar_warehouse/bookkeeping/clean/engine.py` | `Bookkeeping.observation(run_id)` and `runs(..., before=...)` are absent. Main has bounded `status()` and `runs(limit, state)` instead. |
| `edgar_warehouse/bookkeeping/clean/storage.py` | The single-query sanitized aggregate observation and `before` cursor pagination are absent. Main has bounded `status()` reads and ordinary `runs()` ordered by `created_at desc, run_id`. PR #1432’s corrected UUID tie-breaker is not in main. Main’s `status()` also does not return the branch’s `failed_steps` aggregate. |
| `edgar_warehouse/cli.py` | `observe loads` top-level command wiring is absent. |
| `skills/bookkeeping/OBSERVABILITY.md` | Absent; no observer operating guide is shipped. |
| `skills/bookkeeping/SKILL.md` | The branch’s observer-specific addition is absent. |
| `tests/storage_adapters/test_bookkeeping_reads.py` | The branch’s regression/read coverage for observation and run paging is absent. Main retains separate storage status tests, not this branch’s cases. |
| `tests/unit/test_bookkeeping_observation.py` | Absent. |
| `tests/unit/test_load_observer.py` | Absent. |
| `tests/unit/test_load_observer_cli.py` | Absent. |

Some lower-level Bookkeeping control/storage code has since evolved (notably [#1237](https://github.com/paulananth/edgartools-platform/pull/1237), and #1501), but the observer’s distinct contract and its regression tests did not land. PR #1432’s storage delta also removed `failed_steps` from ordinary `status()` and changed retry/contention behavior; these changes are not needed by the current explicit publication route and should not be transplanted without a current requirement.

## What current main provides

- `edgar_warehouse/rules/cli.py` defines `_bookkeeping_status()` and `_catalog_run_status()`. The command reads bounded Bookkeeping status for one specified run, maps it to the configured target Pipeline, publishes to `/api/v1/pipelines/{fqn}/status`, and verifies `pipelineStatus` readback. `skills/openmetadata/SKILL.md` (Pipeline execution boundary, around lines 470–503) explicitly says this is an operator-invoked publication after a transition, not an automatic Bookkeeping callback or pipeline trigger; OpenMetadata stores only the latest Pipeline status.
- `edgar_warehouse/bookkeeping/clean/engine.py` exposes `Bookkeeping.status(run_id, limit, step)` and bounded `runs(limit, state)`. `edgar_warehouse/bookkeeping/clean/storage.py` backs them. There is no `observation()` API or observer pagination cursor.
- PR #1484 added the quality aggregation/result path across `bookkeeping/clean/quality.py`, the Rules catalog/CLI, silver writer/landing, and unit tests. PR #1588 records proof of completed-run per-load quality publication. This addresses quality evidence explicitly marked `not_reported` by #1432, but it does not create a recurring status reporter.
- The #1635 closeout report at `.planning/workstreams/openmetadata-sync-closeout-20261110/RESEARCH.md` already summarizes #1507’s latest-status capability and distinguishes it from continuous progress reporting. Reuse that established boundary rather than copying its API/schema analysis here.

## Capability disposition

| Capability from #1432 | Current state | Disposition |
| --- | --- | --- |
| Read/publish one named Bookkeeping run’s latest Pipeline outcome with readback | Implemented by `rules catalog status --bookkeeping-run` and documented by #1507 | Use the current command; no duplicate implementation. |
| Publish verified per-load quality results | Implemented in #1484 and demonstrated in #1588 | Use the quality-result path; it is independent of status polling. |
| Discover all recent runs, produce a sanitized aggregate snapshot, and publish repeatedly on an interval | Not represented in source, tests, or shipped bookkeeping skill on current main | Residual capability. No current-main evidence makes it an active requirement; retain as a separate deferred follow-up pending an explicit need and an owner for scheduling/host coordination. |
| Preserve durable history of every attempt in the OpenMetadata Pipeline status | Not guaranteed; status is latest-only and Bookkeeping status reflects current run/work-item state | Do not promise this from the observer proposal or current status command. |

## Repository evidence inspected

- Current base: `origin/main` at `5dd4d691259a7d6f96f03dcbea45020ab34ede9a`.
- PR #1432 head and complete path diff: `04c3e9c3f392b21c36b89fa9c4a7058cf51f2a42` versus current main; Git path/stat comparison confirms all 12 entries above.
- Later merged commits: #1484 `8d41e29e01ea30f462fd8612e25d08a5cf3f1033`; #1588 `0ba59a44f068790c5da4aa6c3962805b44e7f99d`; #1507 `f65c6e14cc0b955dcfd7b7ea9809bbf2ecc2dafd`; #1635 `511973670a4ecaac2d03aa728793f0b51ebbc632`.
- Current symbol/path search across `edgar_warehouse`, `skills`, and `tests` found no `observe loads`, `load_observer`, `OBSERVABILITY.md`, or `Bookkeeping.observation()` implementation.
