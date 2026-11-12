# Quality result history

For per-load publication, the normal `rules catalog publish` workflow accepts
`--bookkeeping-run RUN_ID`; it reads verified receipts from a completed
Bookkeeping run and reconciles the configured catalog plan. Use this publisher,
not a separate hand-written API procedure.

For each case and load, this publisher sends a result to
`POST /api/v1/dataQuality/testCases/testCaseResults/{caseFQN}` with `timestamp`,
`testCaseStatus` (`Success` or `Failed`), `result`, `passedRows`, `failedRows`,
and `testResultValue`.
The publisher reads the exact timestamp back with
`GET /api/v1/dataQuality/testCases/testCaseResults/{caseFQN}?startTs={timestamp}&endTs={timestamp}`
using the FQN as one URL-encoded path segment. Require exactly one row with
that timestamp; compare all six fields. `testResultValue` has `rowsChecked` and
`rowsFailed` name/value entries with string values; `passedRows` is
`rowsChecked - rowsFailed`. A successful HTTP response alone does not confirm
publication.

OpenMetadata history timestamps have millisecond precision. When multiple
work units for one case share the same observed millisecond, assign deterministic
adjacent millisecond history keys so each load remains distinct. Preserve each
receipt's original observation time in the result detail; the API timestamp is
the unique history key, not a replacement for that observation time. Read back
each exact assigned key before reporting confirmation.

Treat an identical result at the same timestamp as an idempotent replay.
Duplicate or mismatching history is an error to resolve, not a reason to POST
again blindly. On OpenMetadata 2.0.2, a timestamp-specific `PATCH` can correct
one mismatching result; make at most one correction attempt, then require exact
readback.

## Capturing results before a reset

A catalog reset deletes the owned quality cases, and their results go with
them. The publisher restores results from a `--results` file or a
`--bookkeeping-run`; it cannot rebuild them from the server it just emptied.
Capture them first: for each owned case,
`GET /api/v1/dataQuality/testCases/testCaseResults/{caseFQN}` returns every
result row it holds. The response rows carry the server's own fields
(`timestamp`, `testCaseStatus`, `result`, `passedRows`, `failedRows`,
`testResultValue`); the `--results` file wants a different shape, so convert
on the way out. Each entry under a case name carries `rows_checked`,
`rows_failed`, `on_fail` (`flag` or `exception`) and `at` (an ISO 8601
instant), plus the optional `correlation`. `passedRows + failedRows` is
`rows_checked`. The `result` text carries the load reference after `Load: `,
which is the `correlation`; keep it, because it identifies the load. The
publisher rebuilds the server's `result` text from these fields, so it does
not need the captured text itself.
Remap a case whose source version moved to the plan's current name, then
republish and require the readback to confirm every result.

This API behavior does not establish that the platform supplied complete,
verified evidence for the load. Preserve an incomplete run as unknown, and
publish only results backed by admitted load evidence.

## What the shipped UI shows

Verified in the browser against OpenMetadata 2.0.7.

- The Test Case Results tab shows the **newest** result's full text, so the
  Bookkeeping run, step, work unit, attempt and observation time are readable
  there. The publisher puts that load reference in the result detail, which is
  what makes the newest load identifiable.
- History is a **chart**, not a list: one point per result over a 30-day axis,
  with `rowsChecked` and `rowsFailed` series. There is no per-point tooltip and
  no result table, so an **older** load's result text is not readable in the
  UI. Read it through
  `GET /api/v1/dataQuality/testCases/testCaseResults/{caseFQN}`.
- The states an operator can see are confirmed (`Last Run Success`), failed
  (`Last Run Failed`, with the failed-row count and an incident), and never run
  (`Last Run Not run yet`, an empty chart, and "We couldn't find any test
  results from Last 30 days.").
- The result status vocabulary is `Success`, `Failed` and `Aborted` only; the
  server refuses `Pending` and `Unknown` with HTTP 400. A pending or
  incomplete load therefore cannot be presented as confirmed publication, and
  a publisher that refuses incomplete evidence leaves the published history
  unchanged.
- The Test Cases list, the Test Suites list and a table's Data Quality panel
  show the last run or a summary only. None of them shows per-load history.
