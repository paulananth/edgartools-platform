Type: research
Status: resolved

## Question

`bronze_seed_silver_gold`'s `BatchSilver` Map calls `bootstrap-batch` once per
100-CIK batch, and each call ends with a `merge_candidate_into_canonical`
publish. Ticket 05 already decided "leave it" for this exact merge function,
but that decision was scoped to `ReduceIdentityRefresh` (4 candidates,
187.9s total, ~1.4% of a 225-min run). Does the same "leave it" conclusion
hold when the same function runs hundreds of times in one pipeline, or does
`bootstrap-batch`'s candidate count change the cost/benefit enough to justify
revisiting the storage path for this caller specifically?

## Evidence (confirmed live, 2026-08-07/08, prod, new Snowflake-account cutover)

Timed one full `BatchSilver` batch (100 CIKs, all cache hits, zero SEC calls,
`edgartools-prod-large` task, 8192MB) end to end via CloudWatch:

| Phase | Duration | Scales with |
|---|---|---|
| Container start + hydrate silver from S3 | ~33s | fixed per task |
| Bronze capture (230 cached objects) | 54s | CIK count |
| Silver apply | 9s | CIK count |
| **Copy canonical DB locally + ATTACH** | **~20s** | canonical file size (>1GB) |
| **Merge loop across 21 protected tables** | **~31s** | canonical row counts, not this batch's contribution |
| **Upload merged DB back to S3** | **~45s** | canonical file size |

Total: ~3m38s wall clock for one batch. `BatchSilver` in this run has 679
total batches at `MaxConcurrency=4` — roughly 679 × 3.5min ÷ 4 ≈ **10 hours**
for this one stage alone, before `MdmRun`/`MdmBackfill`/`MdmSync`/
`MdmVerify`/`GoldRefresh` even start.

Within the 31s merge loop, `sec_thirteenf_holding` (6.8M rows) cost only
6.8s — smaller than `sec_company_filing` (4.7M rows, 21.6s), and every one
of the 21 tables gets a full pass on every batch regardless of whether that
batch's 100 CIKs contributed any rows to it. The skip condition
(`if table_name not in cand_tables: continue`) only checks schema presence,
not row relevance — `bootstrap-batch` always creates the full silver schema
per candidate, so no protected table is ever actually skipped in practice.

The two `shutil.copy2`-adjacent steps (copy-in, publish-out — ~65s of the
~95s publish phase, 68%) are the dominant cost, and both are O(canonical
file size), not O(this batch's data) — they cost the same whether a batch
contributes 1 row or 10,000.

## Related, smaller finding (same investigation, not the primary question)

`edgar_warehouse/application/warehouse_orchestrator.py` has a second, dead
`run_seed_universe_command` function (distinct from the one actually wired
to the CLI via `command_router.py` → `COMMAND_REGISTRY["seed-universe"]`)
that calls `_resolve_seed_document`/`_resolve_seed_limit` — neither is
defined anywhere in the repo. Unreachable today, so harmless, but would
`NameError` immediately if anything ever called it. Worth deleting in the
same pass as whatever this ticket decides, not worth its own ticket.

## Why this wasn't answered already

Ticket 05 explicitly scoped itself to `ReduceIdentityRefresh`'s measured
187.9s/4-candidate case. The parent map's "Not yet specified" section
already flagged `bootstrap-batch`'s own non-SEC-fetch stage breakdown as
unprofiled, deprioritized on the assumption that existing `MaxConcurrency=4`
fan-out would absorb whatever this breakdown revealed. That assumption
doesn't hold here: fan-out parallelizes *across* batches, but each
concurrent worker still pays the full ~65s copy-in/publish-out round trip
against the *same* growing canonical file — more workers means more
concurrent full-file S3 round trips, not a smaller per-batch cost.

## Answer (2026-08-08, live evidence from the just-completed medium/20 run)

**"Leave it" still holds, but not for ticket 05's original reason — the
question this ticket asked is now moot.** CIK-range sharding (implemented
directly out of the wayfinder ticket flow, mid-cutover, under explicit
"this cannot wait" instruction — see ticket 12's context) already replaced
the exact cost mechanism this ticket was investigating: the copy-in/
merge/upload round trip is no longer O(one growing >1.6GB monolithic
canonical file) — it's O(one ~80-800MB shard), and every `BatchSilver`
task now touches exactly one shard, not the whole canonical DB.

Pulled a real end-to-end task trace from the just-completed
`bronze-seed-silver-gold-medium-20-retry-1786214600` run (task
`12ccb0199ee141eb9a6b6597d52163dc`, run_id `fd28cdcc-...`, a 14-CIK batch
against `shard-2.duckdb`, 249,835,520 bytes / ~238MB) via CloudWatch Logs +
`ecs describe-tasks`:

| Phase | Duration | Compare to ticket 11's original (100-CIK, pre-shard) estimate |
|---|---|---|
| ECS provisioning (created → pull started) | 15.3s | not itemized originally |
| Image pull | 13.2s | not itemized originally |
| Pull stopped → container started | 5.3s | (these three ≈ old "~33s container start") |
| Container started → shard hydrated | 11.3s | was "copy canonical DB locally + ATTACH ~20s", now downloading one shard (238MB) instead of the whole >1GB+ file |
| Bronze capture | 1.9s | was 54s/100 CIKs (≈7.6s at this batch's 14-CIK scale) — still faster even scaled down, all cache hits |
| Silver apply | 0.4s | was 9s/100 CIKs (≈1.3s scaled) |
| **`silver_publish` (merge across 21 tables + upload)** | **3.2s** | **was ~31s (merge) + ~45s (upload) = 76s combined, unscaled — now one order of magnitude smaller even before accounting for the smaller batch size** |
| Teardown (publish complete → task stopped) | 25.5s | not itemized originally |
| **Total task wall time** | **77.4s** | **was ~3m38s (218s) for one 100-CIK batch, before teardown** |

The merge loop itself still does a full pass over all 21 protected tables
regardless of batch relevance (the same behavior this ticket originally
flagged) — but "full pass over a table" now means a full pass over that
table's rows *within one ~238MB shard*, not within the >1.6GB+ monolith.
The absolute cost dropped in proportion to the file-size reduction sharding
already delivered, independent of anything ticket 05 decided about the
merge function's internal structure.

**No further storage-path work is justified for `BatchSilver`.** The
remaining ~46s of this task's 77.4s (provisioning + pull + teardown) is
fixed ECS/Fargate task-lifecycle overhead, not merge-storage cost — that's
exactly the "61% of each task is fixed overhead that parallelizes for free"
lever tickets 12 and 13 already used to justify `MaxConcurrency=20`, not a
new axis this ticket needs to open. If `BatchSilver` throughput ever needs
to scale further, the lever is more shards or higher `MaxConcurrency` (see
this map's "Not yet specified" entry on scaling beyond today's 4 shards),
not revisiting `merge_candidate_into_canonical`'s storage path a second
time.

**Related smaller finding (unresolved, still true, still not worth its own
ticket):** the dead `run_seed_universe_command` function in
`warehouse_orchestrator.py` (calls undefined `_resolve_seed_document`/
`_resolve_seed_limit`, unreachable via `command_router.py`) was not touched
by this investigation — leaving it as a one-line note for whoever next
edits that file, per the original ticket's own assessment.
