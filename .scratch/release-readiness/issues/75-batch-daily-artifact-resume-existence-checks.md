Type: task
Status: open

## Question

`daily_artifact_resume.py`'s `prepare_resume` loops over every selected
accession and calls `_exists_json` twice per candidate -- once for
`succeeded`, once for `terminal_repair_required` -- each a separate S3
`GetObject` existence check. Should this become a batched check?

## Root cause

Found while resolving [pipeline-throughput-architecture ticket 01](../../pipeline-throughput-architecture/issues/01-profile-pipeline-stage-bottleneck-breakdown.md)'s
profiling pass, using real timestamps from
`daily-incremental-ticket70-verify-1785720814`'s first attempt (ECS task
`04188c2d7c554cb68b48404fa4e2c2a1`): the gap between
`daily_artifact_selection_completed` and `daily_artifact_resume_loaded` was
**307.7s for 5,097 candidates** (~60ms/candidate, ~10,194 sequential S3
existence checks) -- the same unbatched-per-row-of-S3/DB-calls shape as
[tickets 67](67-fix-authority-column-false-positive-conflicts.md),
[68](68-batch-daily-index-filing-merge-inserts.md),
[69](69-reuse-s3-client-in-artifact-fetch-loop.md), and
[72](72-batch-company-sync-state-seeding.md) -- just not yet applied here.

Smaller than those (a fixed ~5-minute cost per `daily-incremental` run, not
scaling with candidate volume beyond the current ~5K range), but real and
silent, same as ticket 72's reasoning for why it was still worth fixing
despite being bounded.

## Not yet specified

Whether S3 supports a genuinely batched existence check here (`ListObjectsV2`
with a prefix covering all candidates' outcome paths in one call, then a
local set-membership check, instead of one `GetObject` per candidate per
status) -- needs to be worked out against the actual key layout
(`daily_artifact/runs/<run_id>/outcomes/<accession>/<status>.json`) before
this is a precise implementation ticket.

## Done when

A decision on the batching approach, implemented and verified against real
data, following the same TDD/DB-backed (here: S3-backed or a fake matching
real key layout) test discipline as tickets 67-72.
