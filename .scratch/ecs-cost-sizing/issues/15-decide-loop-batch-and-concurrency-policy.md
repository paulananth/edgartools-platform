# Decide the Loop, Batch, and Concurrency Policy

Type: grilling
Status: resolved
Blocked by: 07, 12, 13

## Question

For each loop class, what batch or window size, records-per-item range,
`MaxConcurrency`, retry budget, timeout, failure tolerance, and backpressure
rule best balances throughput, correctness, quotas, memory pressure, and cost?

Decide explicit policies for CIK batches/windows, filing/accession work,
relationship types, generation partitions, graph sync, and verification. Use
observed records per item and per execution rather than a universal batch size.
Preserve sequential execution where canonical publication, DuckDB writers,
Snowflake Postgres contention, SEC rate limits, or graph consistency require
it; otherwise prioritize reducing the end-to-end critical path through measured
parallelism, batching, and quota headroom. Prefer the fastest correct complete
configuration on the accepted cost frontier, not the lowest-cost configuration
in isolation.

## Answer

Six loop classes, decided against Ticket 12/13's measured evidence rather than
a universal batch size, per the question's own instruction:

**1. CIK batches/windows (`load_history`'s `compute-windows`/`WindowedBootstrap`)
— the loop that triggered this ticket.** Currently `MaxConcurrency:1` by
design (protects against the `silver.duckdb` promotion race that got
`bootstrap_batched` deleted entirely — correctly preserved, not revisited).
The real gap: **no cross-execution resumability**. Every `load_history` retry
rebuilds its window index from the full `get_tracked_ciks("active,
bootstrap_pending")` universe, unconditionally — `claim_discovery_ciks` only
guards against *concurrent* collision, not "already finished by a prior,
completed run." Confirmed live: retry5's `WindowedBootstrap` fully succeeded
(53/53 windows, ~5,300 CIKs, 201,154 silver rows, $1.69, Ticket 13) — retry6
was about to reprocess that same set from scratch, redoing rate-limited
`MaxConcurrency:1` SEC discovery calls for companies already durably
captured, directly against Ticket 10's now co-primary "speed to complete,
validated output" objective.

**Decision: build opt-in cross-run resume** (`--resume-ledger-run-id` on
`compute-windows`/`bootstrap-next`), mirroring `BatchSilver`'s existing
`compute-remaining-batches` precedent — filter `get_tracked_ciks(...)`
against `discovery_checkpoint` rows already `status='succeeded'` under the
named prior run. Simpler than `BatchSilver`'s version: `load_history`'s
`MaxConcurrency:1` windows already write straight to the shared
`discovery_checkpoint` table, so no new S3 done-marker system is needed —
just a new read path. Deliberately opt-in, not automatic/time-boxed, to keep
resume an explicit operator choice (matches this repo's existing convention;
also keeps freshness re-checks possible when genuinely wanted). Out of this
map's planning-only scope to build — flagged as a required follow-up PR, not
done this session.

**2. Filing/accession loop (inside `WindowedBootstrap`).** Already tuned
across several resolved incidents this session
(`WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY=5`, `WAREHOUSE_ARTIFACT_REQUEST_DELAY`
lowered to 0.2s, `network_fetches`-gated throttling, bronze-recovery-from-S3
for the document-byte layer specifically). **Decision: ratify as-is, no
change** — no unresolved evidence points at a problem here, unlike the
CIK-window layer above.

**3. Relationship-type backfill (`mdm backfill-relationships`, 11 types).**
No concurrency knob exists today — `backfill_relationship_instances`
(`edgar_warehouse/mdm/graph.py:376`) iterates all 11 types sequentially in
one process, one Postgres session, no threading. Real non-zero backfills
take 33–99 minutes per type (Ticket 13). **Decision: stay sequential** —
this is a bounded utility off `load_history`/`daily_incremental`'s critical
path, not currently a bottleneck workflow; the wall-clock gain from
parallelizing doesn't clear the bar against introducing unproven
write-contention risk on the shared `mdm_relationship_instance` table.

**4. Generation partitions (`generation_build`'s `BuildPartitions` Map).**
Already has a concurrency setting, `MaxConcurrency:8`
(`--mdm-generation-partition-concurrency`, deploy script default) — but it's
only ever been exercised once, 21 days ago, so the default has zero
validation evidence behind it. **Decision: defer** — sizing an untested Map
for a workflow whose keep/retire status is still one of Ticket 14's two open
items is premature. Contingent on Ticket 14's `generation_build` call.

**5. Graph sync (`mdm sync-graph`).** **The sharpest finding of this
ticket.** Default `--mdm-graph-limit` is 200; every observed execution has
hit that ceiling exactly (100/100, 200/200 nodes/edges) and stopped, with no
evidence of a repeated drain loop anywhere in the 30-day execution history (6
runs total). Ticket 12 found `MANAGES_FUND` alone backfilled up to 563,631
relationship rows — draining just that one type at 200/run would take
~2,818 sequential invocations. Against CLAUDE.md's documented ~193,323-node
real graph, **no production-scale graph sync appears to have ever actually
run** — this is not a tuned production setting, it's an unexamined
smoke-test default nothing has outgrown because nothing has tried to run
past it. **Decision: raise `--mdm-graph-limit` to 0 (unbounded) for
production-scale `sync-graph` runs**, keep 200 only for the smoke-test/E2E
driver. The `0 = no limit` behavior is already supported by existing code —
no new code needed, just a different launch value. However: nobody has run
`sync-graph` unbounded before, so its duration/memory profile at real
(~193K-node) scale is unmeasured. Requires one canary run before this
becomes the deployed default — folded into Ticket 16 (machine-profile-per-
stage) as a required precondition rather than flipped blind.

**6. Verification (`mdm verify-graph`).** Confirmed via source
(`edgar_warehouse/mdm/cli.py:1575`, `_handle_verify_graph`) to be a single
bounded SQL-check pass, not a batched or looping construct — no batch size,
concurrency, or backpressure rule applies. **Decision: no policy needed**;
already covered as a non-record-based control-plane utility (Ticket 13's own
classification).

**Net effect on retry6, the concern that opened this ticket:** items 1 and 5
are real, evidenced problems — but neither blocks retry6 from completing
correctly today. Item 1's fix (cross-run resume) is a follow-up PR, not
built this session; item 5's fix (unbounded graph sync) needs a canary
before deployment. Retry6 can launch now paying the known redundant-
discovery tax on its CIK-window stage, or wait for the resume fix — that
launch-timing call is the operator's, not resolved by this ticket.
