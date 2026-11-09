# 208: Step 5: field values by survivorship

Priority: 208. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 14:34 ET (operator: "Create ticket for each step and prove it to me that it works start with step 1").

Type: task, with a proof. Status: open. Blocked by: none.

## Question

Does the engine do this, and can each part be shown to work?

## The approved step

Field values are chosen by survivorship, one field at a time, after the golden record is settled. Source priority, declared per entity type in the mastering policy, decides which source's value survives. It plays no part in deciding which golden record a source record belongs to. Every source's value, including the ones that did not survive, is kept.

(CONTEXT.md, "Mastering", approved by the operator one step at a time, 2026-11-09.)

## Where it lives today (from reading `edgar_warehouse/mastering/merge.py`, 2026-11-09 14:34 ET)

`_write_masters` calls `prepare_master_records` with the policy's source priority after the match. `check_source_priorities` validates it. Not verified: that every losing value is kept.

## Checklist

- [ ] Prove source priority never changes which golden record a record joins: the same records in two priority orders give the same golden records.
- [ ] Prove the winner per field follows the policy, one test per entity type.
- [ ] Prove every losing value is kept and can be read back.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
