# Decide the Cutover Validation Standard

Type: grilling
Status: open

## Question

Three separate read-path swaps are in scope on this map: MDM's
`ShardedSilverReader` → Snowflake GRANTs (Ticket 02), gold's Python
builders → dbt `ref()`ing dbt silver (Ticket 03), and `bootstrap-batch`'s
sharded write mechanism → Snowflake landing zone (Ticket 04). Each needs to
prove its Snowflake-backed replacement produces equivalent results before
its DuckDB path is deleted — but "equivalent" hasn't been defined, and
without a single shared bar, each of those three tickets would likely
invent its own ad hoc standard, drifting in rigor and making the eventual
sign-off inconsistent.

Decide the proof standard uniformly, so Tickets 02/03/04 each apply it
rather than re-deciding it: What counts as sufficient parity (row-count
match? column-level diff? a sampled reconciliation? full shadow-run
comparison over N days)? Over what window/volume of real data? Who/what
signs off (an automated assertion that gates the DuckDB-path deletion, or
a manual review)? Does the standard differ for a read-only swap (MDM,
gold) versus the write-path swap in Ticket 01, which has no "compare old
output to new output" story once DuckDB stops being written at all (there
is no "old" run to diff against for future data)?

## Deliverable

A decided proof standard (or an explicit "differs per consumer, and here's
why" if a single standard doesn't fit), specific enough that Tickets
02/03/04 can each cite it directly rather than re-deriving their own bar.
