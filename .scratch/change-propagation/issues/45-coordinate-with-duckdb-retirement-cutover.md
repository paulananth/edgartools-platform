# 45 — Coordinate this map's acquisition-path cutover with the DuckDB Retirement map's storage-layer cutover

Type: research
Status: open
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
