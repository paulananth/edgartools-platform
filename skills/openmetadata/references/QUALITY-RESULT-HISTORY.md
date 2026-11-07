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

This API behavior does not establish that the platform supplied complete,
verified evidence for the load. Preserve an incomplete run as unknown, and
publish only results backed by admitted load evidence.
