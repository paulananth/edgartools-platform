# 207: Step 4: join, create, or two found

Priority: 207. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 14:34 ET (operator: "Create ticket for each step and prove it to me that it works start with step 1").

Type: task, with a proof. Status: open. Blocked by: none.

## Question

Does the engine do this, and can each part be shown to work?

## The approved step

One golden record found: the source record joins it. None found by any identifier or by the name rule: the entity type's creation rule creates one golden record, or leaves the record waiting. Two golden records found: this is an error, a duplicate already in the store. Mastering runs its matching rules on the two golden records. If they match, the younger is decommissioned, and the older survivor keeps both golden records' identifiers, source records and history, and the source record joins the survivor. If they do not match, the source record stays unjoined with an exception status until a data steward resolves the duplicate.

(CONTEXT.md, "Mastering", approved by the operator one step at a time, 2026-11-09.)

## Where it lives today (from reading `edgar_warehouse/mastering/merge.py`, 2026-11-09 14:34 ET)

One found binds it. None found either mints (`on_no_match: mint`) or waits. Two found: `store.oldest` keeps the older, `repoint` moves the records, the younger becomes an alias. Not verified: that the matching rules run on the two before they merge, and the unjoined exception status when they do not match.

## Checklist

- [ ] Prove one found joins, with a test.
- [ ] Prove none found mints or waits as the entity type's creation rule says, one test per entity type.
- [ ] Prove two found runs the matching rules first, then keeps the older and keeps both golden records' identifiers, source records and history.
- [ ] Prove two found that do not match leaves the source record unjoined with an exception status, and that a data steward can resolve it.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
