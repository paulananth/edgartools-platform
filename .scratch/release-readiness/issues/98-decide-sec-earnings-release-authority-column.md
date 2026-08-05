# Decide an authority strategy for sec_earnings_release GAAP columns

Type: task
Status: open

## Question

Ticket 42's F5 scale-mismatch fix (PR #355, hardened by PR #356) is correct and safe as
deployed, but cannot get its corrected output into canonical prod silver for the 20 sample
CIKs' already-published accessions. `sec_earnings_release` has no `authority_column`, and
`revenue_gaap`/`net_income_gaap` are not `provenance_columns`, so **any** change to these fields
for an already-published `(cik, accession_number)` row — whether a genuine bug fix or a future
regression — is unconditionally treated as an ambiguous same-key conflict by
`_resolve_conflict` (`edgar_warehouse/silver_protection.py`) and blocks the entire run's
publish. Confirmed live 2026-08-05: re-running the hardened fix against the same 20-CIK sample
failed with `30 ambiguous same-key conflict(s) block publication` on exactly these two columns,
even though the new values (nulls, replacing wrong-magnitude numbers) are strictly more correct
than what's currently in canonical.

This is architecturally the same *shape* of gap ticket 97 found and fixed for
`sec_filing_attachment.raw_object_id` — but **not the same fix**. Ticket 97's resolution
(exclude the column from comparison entirely via `provenance_columns`) worked because
`raw_object_id` drift is legitimate, expected, and nothing downstream reads the column directly.
`revenue_gaap`/`net_income_gaap` are the opposite case: they're load-bearing headline financial
metrics that F4/F9/F5 verification explicitly checks for correctness, and a future *real* data
error should still be caught, not silently waved through by a blanket provenance exclusion.

What's the right authority strategy here? Candidates to weigh (not yet decided):

1. **`parser_version`-based authority**: declare `parser_version` (already a column on this
   table) as the `authority_column`, with "higher version wins." A newer parser run can then
   overwrite an older one's output for the same accession, while two runs on the *same*
   `parser_version` still conflict (catching genuine non-determinism/bugs within a version).
   Mirrors how the rest of the registry uses timestamp-shaped authority columns, just keyed to
   parser version instead of wall-clock time.
2. **Explicit one-time backfill/force path**: leave the merge policy as-is (fail-closed for any
   diff), and instead give operators an explicit `--force`/`--repair` flag scoped to this table
   (precedent: ticket 74's `--repair-manifest` mechanism for bronze objects) for deliberate,
   audited corrections.
3. Something else — e.g. a narrower `provenance_columns` exclusion scoped only to `NULL`-to-
   `NULL`-or-value transitions (accepting "we un-published a suspect value" as always safe,
   while still blocking value-to-different-value changes) — not fully designed, may not be
   simpler than option 1.

## Not in scope here

- Re-running the F5 backfill itself once a strategy ships — that's the natural follow-up, not
  part of this decision.
- Any other protected table's authority-column gaps (this ticket is `sec_earnings_release`-
  scoped; a broader registry audit would be its own ticket).

## Current impact while open

Not blocking: all *future* F5 ingestion (new CIKs via `load_history`, `daily_incremental`) is
safe with the hardened parser as deployed (`edgartools-prod-large:135`) — new accessions have no
existing canonical row to conflict against. Blocking: the 20 sample CIKs' 128 already-published
wrong-magnitude rows (documented in
[ticket 42](42-decide-execute-fundamentals-backfill.md)) remain wrong in canonical prod silver
until this ships.
