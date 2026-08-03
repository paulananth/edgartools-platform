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
