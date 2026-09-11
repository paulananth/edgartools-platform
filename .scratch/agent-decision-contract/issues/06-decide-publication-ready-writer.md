# Decide who writes a READY Decision Contract publication

Type: grilling
Status: resolved
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

## Comments

- Q3 (2026-09-11): operator answered `B -> C -> D` (not A). Clarify whether
  that is a ranked pick of one writer, or a sequence of steps.
- Q4 (2026-09-11): one path, one writer. `mdm reconcile` then gold refresh
  then the watermark aggregator writes READY. Only the aggregator writes.
  Reconcile and gold refresh are required inputs.
- Q5 (2026-09-11): READY requires in one row: graph generation matches the
  active pointer, gold as-of, Bronze digest, high-severity reconcile clear
  or waived, non-empty Decision Subject Universe snapshot.
- Q6 (2026-09-11): a moved `GRAPH_ACTIVE_POINTER` **hides** agent-grade
  reads automatically. The old publication row is not rewritten. A new
  READY is required for the new graph generation.

## Answer

Writer: the **watermark aggregator** only. Path: `mdm reconcile` → gold
refresh → aggregator writes READY. Reconcile and gold refresh do not write
the publication row.

READY in one row requires: graph generation matching the live active
pointer, gold as-of (`gold_run_id`), Bronze digest, high-severity
reconcile clear or waived, non-empty Decision Subject Universe snapshot.

If the active graph pointer moves, agent-grade reads fail closed without
mutating the old publication. The aggregator must write a new READY after
reconcile + gold refresh for the new generation.
