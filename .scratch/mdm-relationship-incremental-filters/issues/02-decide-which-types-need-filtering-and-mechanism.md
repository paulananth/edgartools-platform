Type: grilling
Status: resolved (2026-09-06)
Blocked by: 01

**Spawned by:** the map's own charting session — the map's two "Not yet specified" fog items, both requiring Ticket 01's evidence before they can be decided.

## Question

Using Ticket 01's per-type findings (actual filtering shape, real data-volume risk, available source-table timestamp/versioning columns):

1. **Which of the 11 relationship types actually need a real incremental filter**, versus which are low-enough volume that the current full-scan-bounded-by-write-count approach is fine to leave as-is? Not every type necessarily needs to change — the destination is "the ones that need it get fixed," not "all 11 get touched."
2. **For each type that does need it, what checkpoint/filter mechanism** — a dedicated checkpoint table mirroring `sec_daily_index_checkpoint`'s shape, a per-type high-water-mark column already available on the source table (per Ticket 01's inventory), or something else? Different types may reasonably get different mechanisms if their source tables differ enough.
3. Does this decision change state-machine-consolidation Ticket 08's conservative "leave all 4 higher-risk types operator-triggered-only" call, or does it stay right pending implementation of whatever this ticket decides?

Use `/grilling` and `/domain-modeling` per this map's Notes.

## Answer

Grilled over one round, user-confirmed on all four points. Core design
insight (the user's own framing, resolving the biggest open question):
for the CIK/CRD-range-batched types, the full scan *within* a batch is
unavoidable (resolving an entity's relationships genuinely requires every
row for that entity), but *which* batches get processed at all in a given
run doesn't have to be "all of them, every time" -- the input set can be
controlled by what's actually changed since the last successful
derivation.

1. **Generalize to the bounded (Shape 1) types too, not just batched
   (Shape 2).** `IS_INSIDER`/`HOLDS`/`COMPANY_HOLDS`'s existing
   `_bounded_relationship_sql` LIMIT bounds *output* rows written, not
   *input* rows scanned -- on a growing table every run still re-scans
   from row 1. Add the same `WHERE watermark > last_checkpoint` clause to
   their existing `ORDER BY` query. No reason to fix only the visibly
   worse (batched, full-scan) types when the bounded types have the
   identical "always starts from the beginning" problem underneath.
2. **Per-type watermark column:** real `ingested_at` where [Ticket 01](01-confirm-incremental-filtering-status-and-data-volume.md)
   found one genuinely exists (`INSTITUTIONAL_HOLDS`'s pair,
   `EMPLOYED_BY`'s pair); the natural accession-number-based ordering key
   everywhere else that reads a silver table (`IS_INSIDER`, `HOLDS`,
   `COMPANY_HOLDS`, `MANAGES_FUND`'s silver pair) -- relying on this
   platform's established SEC-data-immutability/append-only invariant
   (CLAUDE.md's "SEC data idempotency" section) to make "higher
   accession_number = newer" safe. Avoids a schema migration for the 8+
   types with no `ingested_at`, and reuses ordering these methods already
   compute for other purposes (`MANAGES_FUND` already sorts by
   `crd_number, effective_date, accession_number` for its own "latest
   filing per CRD" comparison).
3. **Checkpoint storage:** one dedicated table (e.g.
   `mdm_relationship_derivation_checkpoint`, one row per relationship
   type: type name, watermark value, watermark column name, updated_at),
   mirroring `sec_daily_index_checkpoint`'s existing pattern -- not bolted
   onto an existing table or a config value, since different types need
   different watermark value types (timestamp vs. accession-number
   string).
4. **Scope to types with real, non-zero data today:** `IS_INSIDER`,
   `HOLDS`, `COMPANY_HOLDS`, `INSTITUTIONAL_HOLDS`, `MANAGES_FUND`,
   `EMPLOYED_BY`, `ISSUED_BY`. Defer `HAS_PARENT_COMPANY`/`AUDITED_BY`
   (Ticket 03's discovery-pipeline gap / SEC-API limitation) and
   `IS_ENTITY_OF`/`IS_PERSON_OF` (zero matching MDM rows today) until
   their own upstream gaps are separately resolved -- an incremental
   filter can't be validated against a table with nothing in it, and per
   Rule 0 there's no evidence yet these need it at all.

**Not yet done:** implementing the checkpoint table, migration, and
per-type wiring this design calls for -- that's a follow-up execution
ticket, not part of this decision. One piece of related but
independent, already-broken code *was* fixed the same session (user
request, not part of this ticket's own scope): `EMPLOYED_BY`'s secondary
`sec_employment_event` sub-query was hardcoding `remaining=None`,
bypassing even the *existing* growing-window LIMIT every other bounded
query already has -- see the accompanying commit for that narrow fix,
which does not implement this ticket's new watermark design, just
restores the pre-existing bounding this method's own docstring already
implies it should have.
