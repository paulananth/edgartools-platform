# 209: Step 6: every decision is recorded

Priority: 209. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 14:34 ET (operator: "Create ticket for each step and prove it to me that it works start with step 1").

Type: task, with a proof. Status: open. Blocked by: none.

## Question

Does the engine do this, and can each part be shown to work?

## The approved step

Every decision is recorded with the rule and mastering policy version that made it, the source records and identifiers it used, and its outcome, so any golden record, and any value it shows, can be explained from its source records.

(CONTEXT.md, "Mastering", approved by the operator one step at a time, 2026-11-09.)

## Where it lives today (from reading `edgar_warehouse/mastering/merge.py`, 2026-11-09 14:34 ET)

`add_decision` records only merges. On the shared store: 9 decisions against 461,455 golden records and 1,316,643 source records (counts, 2026-11-09). Joins and creations leave no decision. The rules version on mastering records is not recorded (ticket 199's open part).

## Checklist

- [ ] Record a decision for every join and every creation, with rule, policy version, source records, identifiers and outcome.
- [ ] Prove one golden record can be explained from its source records through its decisions (a test, then one real example in chat).
- [ ] Prove a surviving value can be traced to the source record that supplied it.
- [ ] Count decisions against golden records on the store after a load: none unexplained.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
