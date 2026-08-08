Type: research
Status: open

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
