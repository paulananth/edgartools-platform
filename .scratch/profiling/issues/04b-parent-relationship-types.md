# 04b Parent relationship types: two types and a basis

Type: task. Phase: A. Blocked by: 04. Map: [map](../map.md). Plan: [plan](../plan.md).

## Why

The data-model review of 2026-10-07 (with the data-modeling skill) found
five names for two ideas:

- `ACCOUNTING_PARENT` and `IS_DIRECTLY_CONSOLIDATED_BY` both mean "direct
  accounting parent"; only the second is filled (GLEIF's own name, mapped in
  `rules/sources/gleif/source.yaml`).
- `IS_ULTIMATELY_CONSOLIDATED_BY` (GLEIF's, filled) and
  `REPORTED_ULTIMATE_PARENT` (declared, filled by no source) both mean "a
  stated ultimate parent".
- MDM writes its calculated ultimate parent as `CALCULATED_ULTIMATE_PARENT`
  (`edgar_warehouse/mdm/clean/relationships.py`, `_ultimate_parents`), a name
  outside the types table.

## Ruling (operator, 2026-10-07 08:35 ET)

The operator said both earlier definitions were bad and asked again with
options, then chose "Two types + basis (Recommended)":

- **Direct accounting parent** (`DIRECT_ACCOUNTING_PARENT`): the one entity
  that consolidates this entity's accounts in its own financial statements
  (IFRS 10 / ASC 810), per scope and time. Basis: `stated`.
- **Ultimate accounting parent** (`ULTIMATE_ACCOUNTING_PARENT`): the top of
  that chain, the highest entity that consolidates it and that no other
  entity consolidates. Basis: `stated` (a source says it) or `calculated` (MDM
  walked the direct parents), side by side, so a disagreement shows.
- GLEIF's names map onto the two types. `ACCOUNTING_PARENT`,
  `IS_DIRECTLY_CONSOLIDATED_BY`, `IS_ULTIMATELY_CONSOLIDATED_BY`,
  `REPORTED_ULTIMATE_PARENT` and `CALCULATED_ULTIMATE_PARENT` go.
- Ownership (who holds its shares) is a separate concept and keeps
  `OWNERSHIP_PARENT`.

## Corporate actions (operator, 2026-10-07 08:37 ET: "It should also consider corporate actions"; then "SUCCEEDED_BY type (Recommended)")

Mergers, acquisitions, spin-offs and reorganisations change an entity's parent
on a date. The parent model follows them:

1. **Periods from the event.** Each parent link's period starts and ends on the
   corporate action's effective date when a source states it (basis
   `stated`), otherwise when the link was first or last seen.
2. **The calculated ultimate parent keeps its history:** a new period each
   time any link in its chain changes, so `--as-of` gives the ultimate parent
   on any date (today it is computed for one instant only).
3. **The events are transaction data** (merger, acquisition, spin-off,
   reorganisation, name change), in silver, linked to the entities; a parent
   period cites its event as evidence.
4. **`SUCCEEDED_BY`:** a new relationship type, the entity that ceased → the
   entity that took it over, with the effective date and basis. It is not a
   parent: the ceased entity's own parent links end on that date, and its
   children's links end unless a source restates them. GLEIF's successor LEI
   (with its entity status) fills it; SEC filings can later.

## Checklist

- [x] Ruling recorded, with the definitions shown to the operator 2026-10-07 08:36 ET
- [ ] GoF consult (relationships.py types and derivation, relationships.yaml, the relationship view)
- [ ] `rules/merge/relationships.yaml`: the two types (direct: hierarchy, cycles invalid, one parent, derives the ultimate parent; ultimate: stated or calculated); the five names removed; `rules/context/definitions.yaml` and `CONTEXT.md` say the definitions above
- [ ] A relationship carries its `basis` (`stated` or `calculated`); `mdm.relationship_context` and `context relationship` show it
- [ ] The derivation writes `ULTIMATE_ACCOUNTING_PARENT` with basis `calculated`
- [ ] GLEIF's mapping (`rules/sources/gleif/source.yaml`, Codex's path): `IS_DIRECTLY_CONSOLIDATED_BY` → `DIRECT_ACCOUNTING_PARENT`, `IS_ULTIMATELY_CONSOLIDATED_BY` → `ULTIMATE_ACCOUNTING_PARENT` (stated): handoff to Codex, or the operator's word to edit it
- [ ] The new Mastering Policy digest, with a peel layer and the evidence (relationship tests on PG16), for the operator's approval
- [ ] `SUCCEEDED_BY`: the type (ceased entity → successor, not a hierarchy parent), its definition; on its date the ceased entity's parent links end, and its children's links end unless restated
- [ ] Parent periods take a stated effective date when the source gives one (`valid_from_basis` / `valid_to_basis` stated), else first or last seen
- [ ] The calculated ultimate parent has periods: recomputed at every change in its chain, so `--as-of` answers any date
- [ ] GLEIF's successor LEI and entity status mapped to `SUCCEEDED_BY` (Codex's path: handoff, or the operator's word)
- [ ] ~~Corporate action events in silver~~ deferred to [06](06-silver-writer.md): they are transaction data, written by the silver writer; a parent period cites its event once they exist (added 2026-10-07 08:38 ET)
- [ ] Review (Standards, Spec, GoF), PR, CI, merge on word
