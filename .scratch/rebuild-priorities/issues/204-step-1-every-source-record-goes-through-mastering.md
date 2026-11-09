# 204: Step 1: every source record goes through mastering

Priority: 204. Map: [Rebuild priorities](../map.md). Opened 2026-11-09 14:34 ET (operator: "Create ticket for each step and prove it to me that it works start with step 1").

Type: task, with a proof. Status: open. Blocked by: none.

## Question

Does the engine do this, and can each part be shown to work?

## The approved step

Every source record goes through mastering. It arrives with its source, its entity type, its identifiers, its fields, its relationships and its source time. Mastering decides which golden record it belongs to, or creates one. No source writes a golden record directly, and no identifier skips mastering.

(CONTEXT.md, "Mastering", approved by the operator one step at a time, 2026-11-09.)

## Where it lives today (from reading `edgar_warehouse/mastering/merge.py`, 2026-11-09 14:34 ET)

All 14 merge steps in `rules/sources` run `mastering.merge`. Some identifiers are kept in the cross-reference table and never searched (ticket 203), for example the N-PORT registrant LEI, which step 3 says mastering must search. The Form ADV, ownership and 13F mastering targets are incomplete (ticket 201).

## Measured on the shared store (2026-11-09 14:40 ET, read-only, counts and public names only)

- Only `store.write_masters` inserts into `mastering_master` (`store.py:219`); it is called only from `mastering/merge.py`, reached by the live worker and by `rebuild.py`. All 14 merge steps run `mastering.merge`. The old `mdm.*` record tables hold 0 rows.
- 1,316,643 source records stored; 0 point at a missing golden record. 1,314,434 are joined or created; 21,415 wait with an open review (21,294 `binding_required`, 121 `conflicting_identifiers`, counted by reason); 2,209 have no golden record and no open review (1,429 Form ADV custodians named only by name, 55 and 725 ownership securities of the two versions). 160,300 more are set aside in `mastering_deferred`.
- The files delivered 1,318,689 records and the store holds 1,316,643: 2,046 not explained (a restated record replacing its earlier version may account for it; not shown).
- By source and entity type, each of the 14 sources lands only in its own entity type, with one exception: one SEC submissions person record (an individual filer) sits on a Company golden record that also holds two Form ADV filings, joined by CIK. That is one record with two entity types, against step 2.
- Per-source, per-type tests do not exist yet.

## Checklist

- [ ] Show that no code path writes a golden record except `mastering.merge`: list every writer of the master tables and name each caller (read the code, then test it).
- [ ] Show every source's records are accounted for: per source, records in = joined + created + waiting + set aside, counts only, on the store.
- [ ] Name each identifier that is kept in the cross-reference table but never searched, and the ticket that changes it.
- [ ] A test per source kind that a record of that source reaches `mastering.merge`, one test per kind.
- [ ] Decide the 2,209 records with no golden record and no open review: do they wait by design, and where is the reason recorded?
- [ ] Explain the 2,046 records delivered but not stored.
- [ ] The person on a Company golden record: which rule joined it, and what the entity type rule says for an individual who is also an adviser.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
