# Decide the Cutover Validation Standard

Type: grilling
Status: resolved

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

## Answer

Adopt this repo's already-established Production Release Readiness
vocabulary (`CONTEXT.md`) rather than inventing a parallel standard —
built and battle-tested for the structurally identical problem (proving one
system faithfully reproduces/replaces another) in MDM-to-graph parity and
BatchSilver reconciliation work.

- **Proof shape: digest-based, not full materialized diff, not count-only.**
  `Table-Specific Reconciliation`'s existing definition already has the
  right mechanism — a canonical semantic-content digest per table, plus
  declared primary-key uniqueness and required-parent integrity. This is
  effectively exact (a digest mismatch means real content differs) without
  the cost of materializing and diffing every row on tables at real scale
  (e.g. `sec_thirteenf_holding`, 6.8M rows). `Per-Type Exact Relationship
  Parity`'s own definition explicitly rules out "aggregate edge count,
  count-only parity" as insufficient — count-only is not an acceptable
  substitute for this map's three swaps either.
- **Window/volume: bounded case-selection, not a calendar soak.**
  `Bounded Idempotency Rerun`'s precedent — a deterministic, case-selected
  rerun across routing bands, volume, boundary, parser, no-op, and
  guarded-publication cases — is the shape Tickets 02/03/04 each apply, not
  "run in parallel for N days." Each ticket's case selection must include at
  least one genuinely large table, not only toy fixtures, so parity is
  proven at real scale at least once, not just structurally.
- **Sign-off: automated fail-closed assertion gates a required human
  approval; neither alone.** The assertion mechanism follows `Release
  Evidence Automation`'s pattern (rejects identity drift or incomplete
  evidence, never manufactures approval on its own) and is the proof feeding
  the decision — but a human still approves before the DuckDB path is
  actually deleted. This map's own charting-time Notes recorded that
  Snowflake silver had only just had its first successful prod dbt run
  hours before charting — "genuinely new, not yet proven under repeated/
  varied load" — which argues for holding this bar now, not relaxing it
  because it's "just" removing a dead code path rather than a customer-facing
  release.
- **Ticket 01 (the write-path swap) is explicitly out of scope for this
  ticket's deliverable.** It has no "old" output to diff against for future
  data once DuckDB stops being written, so a parity standard doesn't fully
  transfer to it — it would need something closer to `Data Integrity Gate`'s
  self-contained correctness proof (idempotency, no contention, structural
  invariants) instead of an A/B comparison. Ticket 01 is also blocked *by*
  02/03/04, so by the time it resolves this ticket's precedent already
  exists for it to explicitly reuse or diverge from — deferred to that
  ticket, not decided here.

Tickets 02, 03, and 04 each cite this standard directly (digest-based
Table-Specific Reconciliation, bounded case-selected rerun including one
large-table case, automated-assertion-gates-human-approval sign-off) rather
than re-deriving their own bar.
