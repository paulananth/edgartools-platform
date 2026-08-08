Type: grilling
Status: resolved

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
`cik_batches.jsonl` in the order it was written -- ascending CIK. Parsed the
full 679-batch list for this run and located the exact crossing point:
`shard-0`'s boundary (`cik_min=0, cik_max=1,384,293` -- one of 4
quartile-derived bands, computed via `approx_quantile` over
`sec_company.cik`, see ticket 11's sibling migration work) is crossed
between **batch 131 and 132**, i.e. the first **~19% of the run (131/679
batches)** executes entirely inside shard-0 before any batch touches
shard-1. (Initial note in this ticket estimated "possibly a majority" from
a 6-batch sample taken early in the run -- corrected here against the full
batch list: quartile-derived shard boundaries mean each shard gets roughly
its proportional ~25% share of batches, not a majority concentration in
shard-0. Still a real problem, just smaller than first estimated.) For that
first ~131-batch stretch, every `MaxConcurrency=2` pair races the identical
shard-0 file; the same will repeat for each of the other three ~25%
stretches once the run reaches them, just against a different shard file
each time -- concurrent slots are never actually spread across *different*
shards simultaneously under CIK-ascending ordering, regardless of shard
count.

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

## Answer (grilling, 2026-08-08)

**Yes, batch generation becomes shard-aware, via Option A (round-robin
interleave at generation time), and this decision bundles the
`MaxConcurrency` raise (2 -> 4) that was the actual point of doing it.**

### Mechanism: round-robin interleave in `_write_cik_universe_batches`

Traced the exact code path: `seed-bronze-batches`
(`edgar_warehouse/application/commands/seed_bronze_batches.py` ->
`warehouse_orchestrator.py:1804`) calls `_list_bronze_submission_ciks`
(`:4933`, sorts CIKs **ascending**, `sorted(ciks, key=int)`) then
`_write_cik_universe_batches` (`:4906`, chunks that sorted list into
100-CIK batches **in the same ascending order** and writes them straight to
`cik_batches.jsonl`). This ascending order is the entire root cause of the
shard-clustering evidenced above -- nothing else in the pipeline reorders
it before `BatchSilver`'s `ItemReader` consumes the file top-to-bottom.

Rejected the alternative (N separate per-shard sub-Maps, real Step
Functions/ASL restructuring) as unjustified extra blast radius for an
identical outcome -- decided via `/gof-refactor-reviewer`-style cost/benefit,
not preference. Chosen mechanism instead: make `_write_cik_universe_batches`
shard-manifest-aware -- split the sorted CIK list into 4 per-shard sublists
first (using `band_for_cik` from the existing shard-migration code,
`edgar_warehouse/application/sharding/shard_manifest.py`), chunk each into
100-CIK batches as today, then interleave the four per-shard batch-lists
round-robin (shard0-batch1, shard1-batch1, shard2-batch1, shard3-batch1,
shard0-batch2, ...) before writing the JSONL. Zero Step Functions/ASL
changes -- `BatchSilver`'s Map definition is unchanged, it just reads a
differently-ordered input file. When a smaller shard's batch list is
exhausted first (shard-3 is ~63MB vs shard-0's ~775MB+, so it will run out
of batches well before the others), round-robin naturally degrades to
cycling only the remaining shards -- no special-casing needed.

**Fallback:** if `shard-manifest.json` is missing, `_write_cik_universe_batches`
falls back to today's plain ascending-order batching rather than failing the
whole `seed-bronze-batches` step -- mirrors the existing read-path pattern
(`shard_manifest_missing_monolith_fallback` on the hydration side). Ascending
batching is still *correct* when there's no sharding to interleave against,
just not optimally scheduled; a hard failure would make this command newly,
unnecessarily dependent on sharding always being present.

### MaxConcurrency: 2 -> 4 (not 16)

Grilled the actual "will this speed things up" question with a fresh
full-phase timeline pulled from a real batch on the live run (task
`1f097e7b7...`, post all three fixes this session already shipped --
parallel cache-hit reads, sharding, `MaxConcurrency=2`):

| Phase | Duration | Shard-related? |
|---|---|---|
| ECS task launch (create -> started) | 32.3s | No -- fixed per-task |
| App init + shard-file download | 11.3s | Partially -- scales with that shard's size |
| Bronze capture | 5.3s | No |
| Silver apply | 15.1s | No |
| **`silver_publish` (the actual promote/race window)** | **4.0s** | **Yes** |
| Task teardown | 26.9s | No -- fixed per-task |
| **Total** | **97.4s** | |

Key finding: the race window sharding already shrank to ~4s out of a 97.4s
per-task budget -- interleaving that 4s away saves almost nothing directly.
**The real lever is that 61% of each task's wall time (32.3s launch + 26.9s
teardown) is fixed per-task overhead that runs free in parallel across
concurrent tasks.** That's what raising `MaxConcurrency` actually buys, and
interleaving is what makes raising it *safe* (without it, more concurrency
just means more collisions on whichever single shard the ascending order
currently has every slot pointed at).

Considered `MaxConcurrency=16` (4x the shard count) and rejected it for now:
by the pigeonhole principle, 16 slots across 4 shards guarantees ~4 tasks
land on the *same* shard concurrently at any moment -- not eliminating the
race this ticket exists to fix, just shrinking it again (smaller, cheaper
retries, but more frequent, an unverified regime never tested above
`MaxConcurrency=2`). Ruled out as an untested 8x jump with a real chance of
reproducing a smaller version of the original 72-retry-storm pattern.
Confirmed subnet capacity is not a limiter either way (250+ available IPs
per subnet, both subnets checked live) -- that risk, at least, is real but
not currently a blocker at this scale.

**Decision: `MaxConcurrency=4`**, exactly matching shard count -- the clean,
provably non-contending case (each concurrent slot maps to exactly one
distinct shard under the round-robin interleave). Projected impact: current
observed cadence is ~65.5s/batch at `MaxConcurrency=2` (679 batches x 65.5s
~= 12.3 hours for the `BatchSilver` stage). If throughput scales close to
linearly at `MaxConcurrency=4` (unverified assumption -- Fargate task-launch
queuing or Step Functions dispatch throughput could become the next
bottleneck, not yet observed above 2 concurrent tasks), that's roughly
**~6 hours instead of ~12** for this stage.

### Scope and rollout

- This is a **decision + spec**, per this map's standing decision-spec-only
  mode -- not implemented in this session. A normal follow-up implements
  the `_write_cik_universe_batches` change, the fallback path, and the
  `MaxConcurrency` bump in `deploy-aws-application.sh`.
- **Does not retroactively affect the currently-running** `bronze-seed-silver-gold-1786192834`
  execution -- its `cik_batches.jsonl` was already written in ascending
  order before this decision. Applies to the next `seed-bronze-batches`
  invocation after the fix ships.
- `_write_cik_universe_batches` has 5 call sites in `warehouse_orchestrator.py`
  (not just `seed-bronze-batches`) -- this fix is shared infrastructure and
  likely benefits other bulk-reprocessing pipelines that call it, though
  which of those other 4 call sites actually feed a Distributed Map with
  real concurrency wasn't verified in this session -- left as fog.
- Explicitly does **not** touch `daily_incremental`'s dominant cost
  (SEC-rate-limited artifact fetching) -- a different bottleneck, unrelated
  to silver-merge contention.
- If throughput needs to scale beyond `MaxConcurrency=4` later, the
  architecturally coherent path is re-sharding to more shards (e.g. 16) so
  the 1:1 slot-to-shard mapping still holds -- not overloading today's 4
  shards with more concurrency than they can cleanly absorb. Left as
  "Not yet specified" fog on the map rather than ticketed now (not sharp
  enough to spec until `MaxConcurrency=4` has real running evidence behind
  it).
