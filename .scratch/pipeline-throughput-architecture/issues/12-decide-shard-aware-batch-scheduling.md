Type: grilling
Status: open

## Question

Now that CIK-range sharding is live (`migrate-silver-shards`, 4 shards,
`shard-manifest.json`, activated in prod 2026-08-08 mid-cutover), should
`BatchSilver`'s batch *ordering/assignment* become shard-aware -- so that
concurrent `MaxConcurrency` slots target different shard files instead of
whichever shard the next CIK-ordered batch happens to fall in -- and if so,
how (reorder the batch list by shard round-robin, or partition into N
per-shard sub-Maps, or something else)? If yes, is this a prerequisite for
raising `MaxConcurrency` above 2 for `bronze_seed_silver_gold`'s
`BatchSilver`, or a separate, independently-valuable fix?

## Evidence (confirmed live, 2026-08-08, prod, first shard-aware
`bronze_seed_silver_gold` run, `bronze-seed-silver-gold-1786192834`)

Sharding itself is a large, real win: `silver_publish` dropped from 2-6+
minutes per batch (pre-shard, full ~1.6GB+ canonical file, the retry-storm
problem `MaxConcurrency` was lowered 4→2 to fix) to **~8.5s per batch**
against a single ~745MB shard (`shard-0`). Confirmed active via
`silver_shard_hydrated` / `layer: silver_shard` in every batch's logs, no
`shard_manifest_missing_monolith_fallback` fallback event.

But sharding has **not** actually distributed concurrent writers across
independent files yet, because `BatchSilver`'s `ItemReader` consumes
`cik_batches.jsonl` in the order it was written -- ascending CIK. Pulled the
real batch list for this run: the first 6 batches sampled span CIK 1,750
through 71,691, all of which fall inside `shard-0`'s boundary
(`cik_min=0, cik_max=1,384,293` -- one of 4 quartile-derived bands, computed
via `approx_quantile` over `sec_company.cik`, see ticket 11's sibling
migration work). Because low CIKs (older, pre-2000s registrants) are
numerically sparse but data-dense, shard-0 alone will absorb a long,
possibly majority, stretch of this 679-batch run before any batch even
touches shard-1/2/3.

Two of the four completed batches had **overlapping `silver_publish`
windows** against the same shard-0 file (`12:48:11.23-12:48:19.92` and
`12:48:18.03-12:48:26.56`, ~1.9s overlap) with no `PromotionConflictError`
logged this time -- but that's a timing near-miss, not evidence the race is
gone. At `MaxConcurrency=2` today, both running slots are still frequently
racing on the identical shard file; raising `MaxConcurrency` to match the
shard count (4) without also spreading batches across shards would just
reproduce the original 72-retry-storm problem (ticket that drove the 4→2
fix) at smaller (shard-sized, still growing) scale instead of eliminating
it.

## Why this wasn't answered already

Sharding was activated directly, out of the wayfinder ticket flow, under
explicit "this cannot wait" user instruction mid-cutover (see session
history) -- it fixed the per-conflict *cost* (smaller file to copy/merge/
upload) but nobody had yet checked whether it also fixed conflict
*frequency*, which depends on batch-to-shard assignment, not file size.
This map's "Not yet specified" section still lists the pre-sharding
"is DuckDB-file-per-shard even the right primitive" question as unresolved
scope -- this ticket is narrower and now-answerable: given sharding exists,
should *scheduling* also become shard-aware.
