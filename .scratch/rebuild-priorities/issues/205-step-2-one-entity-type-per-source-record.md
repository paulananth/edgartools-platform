# 205: Step 2: one entity type per source record

Priority: 205. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 14:34 ET (operator: "Create ticket for each step and prove it to me that it works start with step 1").

Type: task, with a proof. Status: open. Blocked by: none.

## Question

Does the engine do this, and can each part be shown to work?

## The approved step

Each source record has exactly one entity type: the source's own where it states one, otherwise decided by classification rules. A record whose entity type cannot be decided waits, and no golden record is created for it. Other things the record mentions are relationships to other golden records, resolved when those golden records exist.

(CONTEXT.md, "Mastering", approved by the operator one step at a time, 2026-11-09.)

## Where it lives today (from reading `edgar_warehouse/mastering/merge.py`, 2026-11-09 14:34 ET)

The merge runs per kind (`Settings.kind`). `set_aside` keeps records no rule may master, with a review. Not verified: a classification rule that decides the type for a source that states none, and that an undecided record never creates a golden record.

## Checklist

- [ ] Per source, name where its entity type comes from (the source states it, or a classification rule decides it).
- [ ] Prove an undecidable record waits and creates no golden record: a test with one such record, counting golden records before and after.
- [ ] Prove a mentioned other party becomes a relationship, not a second golden record, and resolves when both exist (one test per relationship kind).
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
