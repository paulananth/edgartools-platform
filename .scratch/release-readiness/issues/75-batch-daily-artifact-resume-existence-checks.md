Type: task
Status: resolved

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

## Resolved (2026-08-03)

Batched via the existing `StorageLocation.find_existing` primitive (already
used by `warehouse_orchestrator.py` for the same "match a glob, get real
paths back" purpose) -- one call to
`find_existing(f"daily_artifact/runs/{run_id}/outcomes/*/*.json")` per
`prepare_resume` invocation, replacing `_exists_json`'s per-candidate,
per-status `GetObject`+JSON-parse. The result is parsed into
`accession -> {statuses present}` by splitting each returned path (no
content read needed -- only existence and which status file it is), then
`prepare_resume`'s loop does a local dict lookup per candidate instead of a
network round-trip.

Removed `_exists_json` entirely (its only two call sites were both in
`prepare_resume`); `_read_json`/`_valid_repair_attestation` are unchanged --
repair-attestation content still needs a real targeted read, but that only
happens for the (small) terminal-repair subset, which this ticket didn't
scope to batch.

Two new tests in `tests/unit/test_daily_artifact_resume.py`:
`test_resume_checks_outcomes_with_one_batched_listing_not_per_candidate`
(40 selected accessions, none with outcomes yet; monkeypatches both
`find_existing` and `read_bytes` to count calls -- asserts exactly one
`find_existing` call and zero per-candidate outcome reads, confirmed to fail
pre-fix with 0 `find_existing` calls since the old code never called it) and
`test_resume_batched_check_matches_per_candidate_categorization` (mixed
succeeded/terminal-attested/terminal-unattested/never-run accessions,
confirms the batched dict-based check produces the same pending/repair
split as the original per-candidate logic). Both pre-existing tests in the
file pass unchanged. Full `tests/unit`+`tests/application`+`tests/architecture`
suite: 1272 passed, 4 skipped, plus the same pre-existing unrelated
`test_go_live_wizard.py` failure noted in ticket 76.
