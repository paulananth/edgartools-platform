# Decide the Concurrent-Writer Model for Snowflake-Native Silver

Type: grilling
Status: resolved
Blocked by: 01

## Question

Does Snowflake's native `MERGE`/transactions fully replace today's app-level
ETag-optimistic-concurrency promotion-and-retry mechanism
(`_publish_silver_database_with_retry`, built specifically after a
2026-07-22 incident where concurrent Distributed Map batches all tried to
publish the same monolithic file and only the first ever won), or does
dbt's own incremental-model refresh semantics introduce a comparable new
conflict class under concurrent writers that needs its own handling?

Once answered: does `MaxConcurrency:1` — currently forced on `load_history`'s
`WindowedBootstrap` specifically to avoid the promotion race this
architecture exists to eliminate — get safely relaxed, and if so to what,
and under what evidence (mirrors `pipeline-throughput-architecture` ticket
12's live-tested-not-assumed discipline for exactly this class of question).

## Answer

**Neither half of this ticket's own either/or is quite right — corrected
by Ticket 01's actual design, the same way Ticket 01 corrected its own
premise.** Snowflake's native `MERGE`/transactions don't "replace" the
ETag mechanism, and dbt incremental-model refresh semantics don't enter
into it (Ticket 01 landed on `dynamic_table`, not `incremental`). The real
answer: **there is no promotion-race conflict class to replace at all**,
because landing writes under Ticket 01's design are plain per-row
`INSERT` into an append-only table, never a whole-file MERGE or swap.
The 2026-07-22 incident's root cause — concurrent Distributed Map batches
all racing to publish/overwrite the *same file* — has no analog once a
write is "add a row" instead of "swap a file."

**Confirmed, not assumed: within one `load_history` execution, Stage 1
windows are guaranteed disjoint at the CIK level.** `compute-windows`
slices one deterministically-ordered CIK list (`ORDER BY cik`,
`silver_store.py:3536-3560`) into contiguous, non-overlapping
`{window_offset, window_limit}` chunks
(`warehouse_orchestrator.py:2653-2667`); each window re-queries that same
live-but-stable list and slices by its frozen offset/limit
(`_resolve_bootstrap_target_ciks`, `warehouse_orchestrator.py:6125-6152`).
`tracking_status` doesn't shift mid-run (Form-15 deregistration only fires
from the daily-index path, never `bootstrap-next`), so two windows in one
run never write the same business key. Cross-execution overlap (e.g.
`load_history` racing `daily_incremental`) is a **separate, already-solved
concern** — the `sec_fetch_active`/`pipeline_run_lease` lease
(`silver_store.py`'s `claim_discovery_ciks`, wired into all four SFNs per
this repo's own recent history) — and it's unrelated to storage format: it
prevents duplicate SEC *fetches* across concurrent commands, doesn't touch
the local DuckDB file at all, and survives this migration unchanged.

### What retires

The entire whole-file candidate/canonical merge apparatus, since nothing
plays its role under the new architecture:
`_publish_silver_database_with_retry`'s ETag-precondition promote-and-retry
loop (`warehouse_orchestrator.py:1108-1151`), `promote_staged`'s
`IfMatch`/`PromotionConflictError` machinery (`object_storage.py:363-430`),
and `merge_candidate_into_canonical` plus the `PROTECTED_TABLE_REGISTRY`/
`authority_column` business-key merge logic it depends on
(`silver_protection.py:585-794`) — superseded by Ticket 01's
`parse_sequence`-ordered window-function collapse, which needs no
per-table authority column at all.

### What stays

`sec_fetch_active`/`pipeline_run_lease` — a different mechanism solving a
different problem (cross-execution duplicate-fetch prevention, not a
storage promotion race). Correcting Ticket 01's Answer, which flagged
*all* 13 operational/excluded tables' disposition as this ticket's job:
too broad. This ticket settled the writer-concurrency/promotion-race
question specifically; `discovery_checkpoint` and the rest of the
operational tables' full disposition remain genuinely unresolved and
undecided by any ticket on this map yet — not silently dropped, just not
in scope here.

### New design point: `parse_sequence` assignment

A **Snowflake `SEQUENCE` object, assigned row-level inside the load
procedure's `INSERT`** (`seq.NEXTVAL` per row) — not a batch-level
`CURRENT_TIMESTAMP()`, which would assign the same value to every row in
one `COPY INTO`/load-procedure invocation and reintroduce ties into the
exact `ROW_NUMBER()`-based tiebreak Ticket 01's design was built to make
unambiguous. Snowflake's metadata layer coordinates sequence allocation
globally — strictly monotonic and collision-free under any concurrency,
no app-level coordination required.

### `MaxConcurrency`: stays at 1, for now

The structural justification for `1` (promotion-race avoidance) is gone —
but this ticket's own text demands live-tested, not assumed, evidence
before relaxing it (mirroring `pipeline-throughput-architecture` ticket
12's discipline), and this map is decision-spec only: nothing is built
yet to test against. Leaving it at `1` isn't a re-endorsement of the old
justification, just a refusal to substitute a new assumption for the old
one. When [Draft Cutover Script and Ownership
Requirements](05-draft-cutover-script-and-ownership-requirements.md) (or
whichever ticket ends up owning implementation/rollout) is ready to
measure it live, it should test upward from the already-proven `2–5`
range documented in CLAUDE.md for `BOOTSTRAP_BATCH_CONCURRENCY` (the same
SEC-rate-limit ceiling applies here, since Stage 1 windows also fetch from
SEC) rather than starting from scratch — but that measurement, and the
final number, is that ticket's job, not this one's.
