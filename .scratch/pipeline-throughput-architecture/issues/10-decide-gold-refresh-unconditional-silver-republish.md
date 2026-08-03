Type: grilling
Status: open

Blocked by: 07

## Question

Should `gold-refresh` (and any other command that never writes to silver)
skip `_publish_silver_database_if_remote`'s unconditional merge/publish
cycle when its local silver copy is provably unchanged from canonical?

## Why this is a real decision, not a mechanical fix

Confirmed live in [ticket 07](07-profile-gold-refresh-stage-breakdown.md):
this single step is **35.9% of gold-refresh's total wall-clock** (60.65s
of 169.12s) -- the largest individual cost in the whole run, bigger than
building all 27 gold tables (33.0%) -- to accomplish literally nothing
(the run's own event confirms `canonical_version == source_version ==
staged_checksum`).

But `_publish_silver_database_if_remote`'s docstring
(`warehouse_orchestrator.py:854-867`) states plainly: "There is no
`--force` parameter on this path -- it cannot bypass the merge or the
concurrency check." That's not an oversight -- it reads as a deliberate
safety choice, and this workstream has already found (tickets 60/63/67)
that this codebase's fail-closed publication paths have earned their
caution the hard way. Before recommending a skip-if-unchanged
short-circuit, the real question is *why* the no-force guarantee exists:
is it purely defensive (never actually needed, safe to add a narrow
provably-safe skip), or does it protect against a real scenario (e.g. a
concurrent writer changing canonical between this task's silver hydration
and its publish step, which an unconditional merge+ETag-guarded-promote
would catch but a naive "skip if local copy looks unchanged" check might
not)?

## What a safe short-circuit would need

If pursued: the skip condition can't be "local silver file hash matches
what we downloaded" (that's trivially true for a read-only command and
proves nothing about whether canonical changed *during* this run) -- it
would need to be "canonical's ETag is still the same one this task read
at hydration time," which is exactly what `promote_staged`'s
`expected_etag` check already verifies **after** the (expensive) merge.
The open design question is whether that same ETag comparison can happen
**before** paying for the merge, for the specific case where the local
silver copy was never written to (a read-only command run), without
weakening the concurrency guarantee for commands that *do* write.

## Done when

A decision -- skip it (and under what precise safe condition), or leave
the unconditional merge as the deliberate safety mechanism it appears to
be -- backed by understanding the concurrency scenario the no-force design
protects against, not just the time savings.

## Sharper root cause found (2026-08-03, answering a direct user question)

Traced the actual merge mechanics rather than just the timing:
`merge_candidate_into_canonical` (`silver_protection.py:548`) only pulls
candidate data into the published output for tables in
`PROTECTED_TABLE_REGISTRY` -- the real business tables. `gold-refresh`
never writes to any of those; it only reads them.

The only tables `gold-refresh` *does* write locally --
`pipeline_run`/`sec_sync_run` (via `complete_pipeline_run`/
`complete_sync_run`) -- are in `EXCLUDED_OPERATIONAL_TABLES`
(`silver_protection.py:253-271`), which the merge loop **never touches at
all**. The output file starts as `shutil.copy2(canonical_path,
output_path)` -- a copy of canonical, not of gold-refresh's local
candidate -- so those excluded-table writes just sit in a discarded local
temp file and never reach canonical. A separate JSON `run_manifest` is
written to S3 independently and appears to be the actual durable run
record.

**This changes the question**: it's not "should we skip the merge when
this run happens to be unchanged" (implying it's sometimes needed) --
gold-refresh's silver-publish step moves **zero bytes of real content on
every single run, by construction**, since neither its reads (business
tables, correctly one-directional per the user's stated requirement:
silver -> gold/MDM/neo4j) nor its local writes (excluded operational
tables) can ever survive this step's own merge semantics. The remaining
open question narrows to: is there *any* other reason this step needs to
run for `gold-refresh` specifically (e.g. does anything downstream expect
`gold-refresh` to have touched canonical silver's ETag/version, even
without content change?), or can it be skipped outright for this command.
