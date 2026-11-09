# 204: Step 1: every source record goes through mastering

Priority: 204. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 14:34 ET (operator: "Create ticket for each step and prove it to me that it works start with step 1").

Type: task, with a proof. Status: open. Blocked by: none.

## Question

Does the engine do this, and can each part be shown to work?

## The approved step

Every source record goes through mastering. It arrives with its source, its entity type, its identifiers, its fields, its relationships and its source time. Mastering decides which golden record it belongs to, or creates one. No source writes a golden record directly, and no identifier skips mastering.

(CONTEXT.md, "Mastering", approved by the operator one step at a time, 2026-11-09.)

## Where it lives today (from reading `edgar_warehouse/mastering/merge.py`, 2026-11-09 14:34 ET)

All 14 merge steps in `rules/sources` run `mastering.merge`. Identifiers marked "lookup only" are stored in `cross_references` and are never searched (ticket 203). The Form ADV, ownership and 13F mastering targets are incomplete (ticket 201).

## Checklist

- [ ] Show that no code path writes a golden record except `mastering.merge`: list every writer of the master tables and name each caller (read the code, then test it).
- [ ] Show every source's records are accounted for: per source, records in = joined + created + waiting + set aside, counts only, on the store.
- [ ] Name each identifier that is stored but never searched ("lookup only") and the ticket that changes it.
- [ ] A test per source kind that a record of that source reaches `mastering.merge`, one test per kind.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
