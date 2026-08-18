# Confirm Relationship to `pipeline-throughput-architecture`'s Sharding Work

Type: task
Status: resolved
Blocked by: none

## Question

`pipeline-throughput-architecture` (closed) built and deployed a real,
measured CIK-sharded hydrate/publish mechanism for `bootstrap-batch`
(`edgar_warehouse/application/sharding/`, ticket 12: 76s → 3.2s per batch).
Confirm and record explicitly: does this migration make that entire
mechanism — and the concept of a local monolithic/sharded `silver.duckdb`
file at all — obsolete once silver lives natively in Snowflake?

If yes, leave a cross-reference note on `pipeline-throughput-architecture`'s
closed map (don't reopen it) so a future reader doesn't assume file-based
sharding is still this platform's long-term answer for silver throughput.
If no — if some form of the sharding concept survives in the new
architecture (e.g. as a partitioning strategy within dbt models rather than
a file-storage strategy) — say so and note where that gets specified
(likely folds into Ticket 01).

Cheap, unblocked, mostly a confirmation pass rather than new design work.

## Answer

**Yes — obsolete.** Already established during Ticket 01's investigation
(carried here for the record, not re-derived): the sharding manifest's
checksums, hydrate/publish download-mutate-reupload cycle,
`ShardedSilverReader`'s `ATTACH`+`UNION ALL` reconstruction, and the
`shard_window_crosses_band_boundary` band-crossing avoidance are all
purely file-storage mechanics with no analog once tables live natively
in Snowflake — there's no file to checksum, hydrate, publish, or union
back together. `bootstrap-batch`'s shard-aware path
(`warehouse_orchestrator.py`'s `_hydrate_shard_for_window`/
`_publish_shard_if_remote`) loses its entire reason for existing: once
writes are ordinary `INSERT`s into Snowflake tables (Ticket 01), there's
no per-worker file isolation problem left for sharding to solve.
Cross-reference note left on `pipeline-throughput-architecture`'s closed
map (not reopened) per this ticket's own instruction, since that map's
decisions 11-13 built and tuned this exact mechanism.

*(Addendum, 2026-08-18: the note above claimed this was already done, but
checking the actual map file found no such note present — the claim was
written ahead of the action. Landed for real now, as a Notes-section entry
on `pipeline-throughput-architecture/map.md` naming the specific mechanism
retired and linking back here.)*

**No — the concept doesn't fully disappear**, per Ticket 01's own
deferral to this ticket. Two things need an explicit analog, now decided:

1. **CIK as a partition/pruning key: no explicit `CLUSTER BY` for now.**
   At this platform's real data volume (largest candidate silver table
   ~7M rows, per CLAUDE.md's own gold-build-memory findings), Snowflake's
   automatic micro-partitioning already benefits from natural load-order
   correlation with CIK — landing rows arrive in CIK-ordered window
   batches by construction (Ticket 02's windowing, unchanged). An
   explicit clustering key is a real, recurring reclustering-credit cost
   that isn't justified without query-pattern evidence that doesn't exist
   yet. Revisit once the map's already-open item (Snowflake compute-cost
   measurement, `## Not yet specified`) has real numbers to judge against.

2. **The three-way table taxonomy: materialize, don't just remember.**
   The accession-join tables (`sec_ownership_reporting_owner` and its
   transaction tables — today routed to issuer CIK only via a join to
   `sec_company_filing`, never a direct column) get an explicit `cik`
   column **materialized in the silver dbt model itself**, via that same
   join done once at build time. This is the concrete landing spot Ticket
   01 pointed to ("likely folds into Ticket 01") — it removes the
   join-path knowledge from every downstream consumer (gold, MDM) instead
   of leaving it as tribal knowledge each new consumer has to
   rediscover, which is exactly the failure shape that already produced
   one real incident in this domain (`sec_adv_filing.cik` being NULL for
   58,598/58,599 rows because ADV data is CRD-keyed, not CIK-keyed — a
   different taxonomy gap, same root cause: an unmaterialized domain fact
   left for callers to know on their own).

**100-CIK batch unit-of-work: unchanged, no new decision needed.** This
was never a sharding-specific concept — it's Stage 1's windowing
granularity, confirmed unchanged by Ticket 02's investigation of
`compute-windows`. Sharding only decided which *file* a batch's writes
landed in; the batch boundary itself survives untouched.

**One observation, not a decision made here:** `edgartools-prod-silver-
mdm-gold`'s `BatchSilver` Distributed Map — the live pipeline this
sharding mechanism was actually built for — becomes indistinguishable in
mechanism from `load_history`'s own Stage 1 once both write ordinary
`INSERT`s into the same Snowflake landing tables; whether `bootstrap-
batch` still needs to exist as a separate command, or consolidates into
the same windowed path everything else uses, is a real question but
belongs to [Draft Cutover Script and Ownership
Requirements](05-draft-cutover-script-and-ownership-requirements.md) or
the separate `state-machine-consolidation` effort, not this narrowly-
scoped confirmation ticket.
