Type: grilling
Status: resolved

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

## Answer (2026-08-03, real measurement + fresh /gof-refactor-reviewer pass)

**Leave the copy2/reattach/per-candidate-merge structure as-is.**

Real cost measured live (ticket 01 didn't cover this stage --
`ReduceIdentityRefresh` is a separate ECS task from `RunWarehouseTask`, so
this ticket's own investigation pulled fresh numbers from the currently
running execution): the entire `ReduceIdentityRefresh` stage -- 4
candidates (1 reference + 3 batch deltas), touching a 6.8M-row
`sec_thirteenf_holding` and 20 other protected tables per candidate,
against a ~1021.8MB canonical file -- took **187.9 seconds total
wall-clock**, ~1.4% of the run's total ~225-minute wall-clock. Smaller than
even [release-readiness ticket 75](../../release-readiness/issues/75-batch-daily-artifact-resume-existence-checks.md)'s
2.5%, which was already judged worth fixing at that magnitude.

The `/gof-refactor-reviewer` pass (re-run fresh; the earlier session's
findings on this exact code were lost to compaction) confirmed the
ticket's original hypothesis was already partly stale:
`_matching_canonical_rows_as_dicts` (`silver_protection.py:431`) is a
**targeted lookup** keyed to candidate business keys, not a full table
scan -- already fixed in an earlier commit (`#211`/`#215`) specifically to
avoid OOM on multi-million-row tables. The per-row `_insert_row`/`_update_row`
loop only iterates the anti-join-filtered delta (genuinely changed/new
rows -- hundreds per table in the observed run, not millions), unlike the
true unbatched-full-table loops tickets 67-72 fixed. `git log` also showed
this exact path has needed 5+ correctness fixes already (provenance-column
exclusions, authority-column false positives, PRIMARY KEY preservation) --
real evidence this is an actively fragile, fail-closed, ETag-guarded path,
raising the regression cost of touching it for a ~1.4% gain well above what
the gain is worth.

**One real, cheap, separate finding did surface and was split off**: in
the same code path, `reduce_identity_refresh`
(`identity_refresh_publication.py:187-209`) fetches every reference/delta
object from S3 **twice** per attempt -- once to checksum-verify (bytes
discarded), once again inside the merge loop to actually use. Low risk,
no correctness-logic change, real savings on every reducer attempt. Filed
as [release-readiness ticket 76](../../release-readiness/issues/76-fix-reduce-identity-refresh-double-fetch.md)
rather than resolved here, matching this map's decision-only mode.

User accepted this recommendation as-is.
