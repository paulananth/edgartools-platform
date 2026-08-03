Type: grilling
Status: open

Blocked by: 01

## Question

Should `silver_protection.py`'s canonical-merge path change from its
current shape -- one full `shutil.copy2` of the growing canonical file per
candidate, followed by a fresh `duckdb.connect` + two `ATTACH`es + a full
`information_schema` walk across `PROTECTED_TABLE_REGISTRY`, per candidate
(`merge_candidate_into_canonical`), plus a per-changed-row Python loop
(`_insert_row`/`_update_row`) -- to attach-once-mutate-many across all
candidates in a run, and/or set-based batched inserts/updates (the same
Arrow-register + `ON CONFLICT` primitive used in [release-readiness ticket
68](../../release-readiness/issues/68-batch-daily-index-filing-merge-inserts.md)
and [ticket 72](../../release-readiness/issues/72-batch-company-sync-state-seeding.md))?

This path is fail-closed and ETag-guarded (protected-table conflict
resolution can legitimately abort a merge), so any redesign must preserve
exact semantics: no silent overwrite, no regression of a canonical-only
row, ambiguous conflicts still abort. Re-run `/gof-refactor-reviewer`
against `reduce_identity_refresh`
(`edgar_warehouse/application/identity_refresh_publication.py:169-238`)
and `merge_candidate_into_canonical` plus its `_insert_row`/`_update_row`/
`_matching_canonical_rows_as_dicts`/`_delta_rows_as_dicts` helpers
(`edgar_warehouse/silver_protection.py:414-599`) as the first step of
resolving this ticket -- a review of this exact code ran earlier in the
session that produced this map but its findings were lost to context
compaction before being recorded anywhere; land the fresh findings as an
asset on this ticket.

Only worth restructuring if ticket 01's profiling shows this path is a
real contributor at current scale (1021.8MB canonical file, 3-4 candidates
per run observed) -- if it's already a small fraction of wall-clock time,
this should resolve "leave it" per the reviewer's own Rule 0.

## Done when

A decision -- redesign or leave it, and if redesign, the target shape --
backed by ticket 01's measured breakdown and a fresh `/gof-refactor-reviewer`
pass with its findings recorded on this ticket.
