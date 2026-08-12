# Decide event granularity for bronze-write triggers

Type: grilling
Status: resolved
Blocked by: 01, 02

## Question

What triggers a downstream silver/gold consumption event: per bronze
object write (~625K+ objects today, per this session's own bronze-layer
size investigation), per accession/filing, per CIK-batch/window (today's
~500-CIK grain), or per logical capture-run? Informed by ticket 01's
silver-write-concurrency facts (does sharding suggest a natural grouping?)
and ticket 02's messaging-substrate facts (per-message cost/volume at each
candidate granularity).

**Scope note (2026-08-11):** company *discovery* (a new CIK entering the
tracked universe via `seed-universe`/`mdm-seed-universe`) is sourced from
SEC's own company index feed, not from a parsed filing — SEC's index is
the system of record for company existence/universe membership, a
different upstream signal from every granularity option above, all of
which assume a bronze-write as the trigger. This ticket does not need to
cover that signal — it graduated into its own ticket, [Finalize the
company-discovery event flow](11-finalize-company-discovery-event-flow.md),
which will decide whether discovery reuses this ticket's chosen messaging
substrate/granularity or uses separate machinery.

## Answer

**Event unit: per-accession, not per-object and not per-window. Bronze
capture emits one event per accession, only once its full configured
document set is captured. The silver-write reducer batches on a fixed
N-or-timer trigger, no meaningful-boundary logic needed.** Decided
2026-08-11.

1. **Per-accession is the event granularity.** Ticket 02 confirmed cost
   doesn't force coarseness — per-object-write granularity is cost-viable
   (under $2 for the full 625K-object backfill) — but cost-viable isn't
   the same as correct. An accession spans multiple bronze objects
   (primary document, exhibits, ownership XML); parsing operates on the
   accession's full document set, matching what [ticket 01](01-research-silver-duckdb-concurrent-write-model.md)
   already established parsing should scale against (fully parallel, no
   correctness constraint per accession). Per-object is finer than any
   consumer needs; per-window is today's coarse grain and undercuts this
   map's own "no multi-day waits" motivation.
2. **Bronze capture emits an explicit accession-complete event, not
   per-object events.** Reuses this repo's existing
   `_configured_parser_accessions` accession-completeness notion rather
   than inventing a new one — individual object writes stay internal to
   bronze capture; they are not what triggers downstream consumption. This
   avoids triggering parse on a partial document set.
3. **The silver-write reducer batches on a fixed N-or-timer trigger — no
   meaningful-boundary batching (e.g. "this CIK's backlog," "this
   window's remaining accessions").** Ticket 02 found EventBridge Pipes'
   SQS batch-size/batch-window gives this natively, no custom scheduling
   logic to write. Ticket 09's reducer merges independent, content-
   addressed deltas regardless of what triggered the merge — the merge is
   safe and idempotent no matter what's batched together, so a
   meaningful-boundary trigger would add complexity with no correctness
   benefit.

**Consumer shape, tying together tickets 01/02/09:** bronze capture
publishes one accession-complete event via SNS; it fans out to two SQS
queues per ticket 02's design — a near-1-batch-size queue driving N
parallel parse workers (ticket 01's "parsing should scale to full
parallelism" requirement), and a larger-batch/timer-windowed queue driving
the silver-write reducer (ticket 09's generalized per-event reducer).

**Unblocks [ticket 07](07-decide-completeness-watermark-signal.md)** —
the watermark's unit of progress is now settled as "per accession
processed," not per-window or per-object.
