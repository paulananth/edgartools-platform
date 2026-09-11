# Decide who writes a READY Decision Contract publication

Type: grilling
Status: open
Blocked by: 03, 04, 09

## Question

`DECISION_CONTRACT_PUBLICATION` is the fail-closed assertion that a watermark
is agent-grade. Who writes it, when, and what makes `PUBLICATION_STATUS =
ready`?

Decide:

1. Writer: warehouse export, MDM reconcile, watermark aggregator, dbt, or an
   explicit operator command.
2. Whether READY requires graph pointer match, gold as-of, bronze identity,
   high-severity reconcile disposition, and a **non-empty** Decision Subject
   Universe snapshot (warehouse-active ∩ MDM-active, from
   [Define the warehouse-active predicate](04-define-warehouse-active-universe-predicate.md))
   in one publication.
3. Whether a moved `GRAPH_ACTIVE_POINTER` automatically hides agent-grade
   rows (as `03_dashboard_contract.sql` does) without rewriting the
   publication row.

This is contract publication mechanics, not ingest orchestration.
