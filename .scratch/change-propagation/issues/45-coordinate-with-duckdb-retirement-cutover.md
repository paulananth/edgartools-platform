# 45 — Coordinate this map's acquisition-path cutover with the DuckDB Retirement map's storage-layer cutover

Type: research
Status: resolved
Blocked by: 10

## Question

[Ticket 10](10-decide-migration-cutover-rollback.md) deliberately deferred
all data-retention questions (superseded DuckDB, mutable landing, and legacy
SOURCE artifacts) to the separate, already-charted
[DuckDB Retirement map](../../duckdb-retirement/map.md), which owns
cutover/rollback mechanics for the storage layer. That map's own destination
is "nothing in the codebase still imports `duckdb`" — a full retirement of
the write/read path this map's own new ledger-gated drivers still target
(via `SilverFinalizer`/`silver_acceptance.py`, which write and read back
`sec_raw_object` through `edgar_warehouse.silver_store.SilverDatabase`,
DuckDB-backed).

These two migrations touch the same physical storage but are being decided
and sequenced independently. Is there a genuine ordering constraint between
them, or are they safely orthogonal? Concretely:

- Does a family's acquisition-path cutover (this map's Ticket 27, once
  Ticket 10's per-family side-by-side verification passes) depend in any
  way on DuckDB still being the live silver target — i.e., would DuckDB
  Retirement's own cutover, if it lands first, break the
  `SilverFinalizer`/`silver_acceptance.py` read-back verification this
  map's new drivers rely on?
- Conversely, does DuckDB Retirement's own cutover depend on this map's
  acquisition-path migration being further along than it is today (e.g.,
  does its plan assume `bootstrap-next` is still the only writer, or does
  it already account for the new ledger-gated drivers as a second writer)?
- If a real ordering constraint exists, which map's ticket should encode
  it, and does either map's existing ticket set need a new blocking edge
  added as a result?

Resolve by reading DuckDB Retirement's current map state (its own
Decisions-so-far and Not-yet-specified sections) directly rather than
assuming either map's framing is still current — same discipline Ticket 10
itself required, since a lot changed underneath this whole area since both
maps were last touched.

## Answer

**A real, one-directional ordering constraint exists — and DuckDB
Retirement's current plan has a genuine blind spot, not just an unstated
assumption.**

Read DuckDB Retirement's map directly rather than trusting this ticket's own
framing: all 8 of its tickets were resolved in a single pass on **2026-08-16**
(`docs(duckdb-retirement): resolve all 8 wayfinder tickets`). Its Domain list
(silver_store.py, sharded_reader.py, silver_protection.py, gold_models.py,
MDM's sharded silver reads, generate_silver_landing_ddl.py, tests/) and its
Ticket 01 answer (atomic write-path cutover, rollback bundles "the write path
+ MDM's and gold's reader cutovers together") **never mention**
`edgar_warehouse/acquisition/silver_acceptance.py`, `SilverFinalizer`,
`filing_artifact`, or this map at all — grepped the whole
`.scratch/duckdb-retirement/` tree, zero hits.

That's not an oversight in the writing — it's chronologically impossible for
it to have been otherwise. `silver_acceptance.py` didn't exist as a live
production caller until this map's own Ticket 46 (`feat(acquisition): wire
filing_artifact's gated capture into daily_incremental`, PR #481,
**2026-08-27** — 11 days after DuckDB Retirement's plan was decided).
Ticket 10 already established the new ledger-gated drivers had "zero live
scheduled presence" as of its own 2026-08-27 grilling; DuckDB Retirement's
plan predates even that.

**The dependency itself, confirmed by reading the code (not inferring from
docstrings):** `silver_acceptance.py`'s two entry points —
`finalize_filing_artifact_candidate` and `drive_filing_artifact_silver_acceptance`
(the one `application/workflows/drive_filing_discovery.py` actually calls) —
both take `silver: SilverDatabase` as a direct, non-abstracted parameter type
(`from edgar_warehouse.silver_store import SilverDatabase`). Its own module
docstring is explicit about *why*: `discovery.py` deliberately avoids this
same `SilverDatabase` dependency to "stay independent of the ~292KB legacy
orchestrator," and `silver_acceptance.py` is exactly the seam that
re-acquires it — by design, for this one family, to write and read back
`sec_raw_object` as "this family's one Silver producer." This is a hard
coupling, not an incidental import.

**Answering the three sub-questions directly:**

1. **Does this map's acquisition-path cutover depend on DuckDB still being
   the live silver target?** Yes. If DuckDB Retirement's Ticket 01 cutover
   (stop writing `silver.duckdb` at all, Snowflake landing zone only) lands
   before `silver_acceptance.py` is ported or retired, `filing_artifact`'s
   Silver-acceptance write-and-read-back — the verification this whole
   module exists to provide — would either write into a DuckDB store nobody
   else reads anymore, or fail outright once Ticket 01's own "bounded
   retention... then archive/delete" disposition removes the file it's
   targeting.
2. **Does DuckDB Retirement's cutover depend on this map's migration being
   further along?** Not on *progress* — on *plan completeness*. DuckDB
   Retirement doesn't need `filing_artifact`'s cutover to reach any
   particular state first; it needs its own Ticket 01 to actually account
   for `silver_acceptance.py` as a caller before it executes, something it
   currently doesn't do at all because the caller postdates the plan.
3. **Which map's ticket should encode it?** DuckDB Retirement's — this is a
   storage-layer cutover completeness gap, squarely that map's own charted
   destination ("cutover/rollback mechanics for the storage layer"), not a
   new blocking edge on this map's side. Nothing in this map (change-
   propagation) is blocked by DuckDB Retirement, and Ticket 27's own
   critical path (per-family removal of legacy bypasses) doesn't touch
   storage-layer choice at all — it can keep progressing regardless.
   Filed as [DuckDB Retirement's Ticket 09](../../duckdb-retirement/issues/09-account-for-silver-acceptance-in-write-path-cutover.md),
   which corrects that map's now-inaccurate "every ticket resolved, ready
   to hand off" claim.

No new blocking edge needed on this map's own tickets — resolving this
ticket is purely a routing/handoff action to the other map.
