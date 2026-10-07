# 04b Relationship types: real names; parents with a basis; corporate actions

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

- **Direct accounting parent** (first named `DIRECT_ACCOUNTING_PARENT`, replaced by `IS_DIRECTLY_CONSOLIDATED_BY`, see Names): the one entity
  that consolidates this entity's accounts in its own financial statements
  (IFRS 10 / ASC 810), per scope and time. Basis: `stated`.
- **Ultimate accounting parent** (first named `ULTIMATE_ACCOUNTING_PARENT`, replaced by `IS_ULTIMATELY_CONSOLIDATED_BY`, see Names): the top of
  that chain, the highest entity that consolidates it and that no other
  entity consolidates. Basis: `stated` (a source says it) or `calculated` (MDM
  walked the direct parents), side by side, so a disagreement shows.
- GLEIF's names map onto the two types. `ACCOUNTING_PARENT`,
  `IS_DIRECTLY_CONSOLIDATED_BY`, `IS_ULTIMATELY_CONSOLIDATED_BY`,
  `REPORTED_ULTIMATE_PARENT` and `CALCULATED_ULTIMATE_PARENT` go.
- Ownership (who holds its shares) is a separate concept and keeps
  `OWNERSHIP_PARENT`.

## Names (operator, 2026-10-07: "All relationships must be named as close as reality do not fabricate names with no meaning"; then each name approved one by one, 2026-10-07 09:08 ET)

The two type names first proposed (`DIRECT_ACCOUNTING_PARENT`,
`ULTIMATE_ACCOUNTING_PARENT`) and `SUCCEEDED_BY` were invented, so they are
dropped. Every name is the one the source's standard uses, checked in the
local GLEIF Golden Copy of 2026-09-11 (relationship file: 126,688
`IS_DIRECTLY_CONSOLIDATED_BY`, 132,877 `IS_ULTIMATELY_CONSOLIDATED_BY`; Level 1:
`SuccessorEntity`/`SuccessorLEI`, and event types `MERGERS_AND_ACQUISITIONS`
44,089, `ABSORPTION` 7,495, `DEMERGER` 786, `BREAKUP` 157, `SPINOFF` 37):

| Name | Approved |
|---|---|
| `ACCOUNTING_PARENT` | Remove it: invented, filled by no source, duplicates the direct parent |
| `IS_DIRECTLY_CONSOLIDATED_BY` | The one direct-parent type, GLEIF's name as written, for any source; each link's basis `stated` |
| `IS_ULTIMATELY_CONSOLIDATED_BY` | The one ultimate-parent type, GLEIF's name; each link's basis `stated` or `calculated`, side by side |
| `REPORTED_ULTIMATE_PARENT` | Remove it: invented; a reported ultimate parent is `IS_ULTIMATELY_CONSOLIDATED_BY` with basis `stated` |
| `CALCULATED_ULTIMATE_PARENT` | Becomes `IS_ULTIMATELY_CONSOLIDATED_BY` with basis `calculated` and the path walked |
| succession | `SUCCESSOR_ENTITY` (GLEIF's term): the ceased entity → its successor, each link with GLEIF's event type and effective date |

The definitions in the ruling above stand; only the names change.

### Every other type (operator, 2026-10-07, one by one, after "Ask again if anything is unclear"; recorded 2026-10-07 09:24 ET)

Evidence: the element names in the installed edgartools parser (Forms 3/4/5
`reportingOwnerRelationship` with `isDirector`, `isOfficer`, `officerTitle`,
`isTenPercentOwner`, `isOther`; 13F `nameOfIssuer`, `titleOfClass`,
`investmentDiscretion`, `votingAuthority` with Sole, Shared, None; XBRL
`AuditorName`, `AuditorFirmId`; "beneficial owner"; Exhibit 21 "Subsidiaries
of the registrant"); the GLEIF Golden Copy counts; ISO 10383 as published (no
MIC file is held locally) and Form ADV as published (no ADV file is held).

| Type today | Approved |
|---|---|
| `EMPLOYED_BY` | Kept, for director, officer (with title) and employee. The ten percent owner leaves it for `BENEFICIAL_OWNER_OF` ("I like employed_by and something devoting ownership") |
| `CONTROLS` | Removed. An adviser's link to what it manages carries discretion, discretionary or non-discretionary (Form ADV Item 5.F), and a 13F holding the manager's investment discretion and voting authority as filed: who decides. Who owns is a separate link (`BENEFICIAL_OWNER_OF`, `HOLDS`). ("Is discretionary vs non-discretionary is how who owns", then "Yes, as shown") |
| `HOLDS` | Kept (SEC's word for both reports); each link says its basis: `investment_discretion` (13F) or `beneficial_ownership` (Forms 3/4/5) |
| `OWNERSHIP_PARENT` | Split: `IS_SUBSIDIARY_OF` (Exhibit 21: subsidiary → registrant) and `BENEFICIAL_OWNER_OF` (Schedules 13D/13G and Forms 3/4/5: beneficial owner → issuer, with the percent) |
| `MANAGES_FUND` | Removed. Two roles, two names ("if it is a fund use fund manager, if adviser use investment adviser"): `IS_FUND-MANAGED_BY` (GLEIF's name, fund → its fund manager, for any source) and `INVESTMENT_ADVISER_TO` (Form ADV and N-CEN's role: adviser → fund, with discretion) |
| `AUDITED_BY` | Kept |
| `ISSUED_BY` | Kept |
| `IS_FUND-MANAGED_BY`, `IS_SUBFUND_OF`, `IS_FEEDER_TO`, `IS_INTERNATIONAL_BRANCH_OF` | Kept as GLEIF writes them |
| `VENUE_OPERATOR` | `HAS_MARKET_OPERATOR`: the market operator (MiFID II's term, the entity that manages and operates the market's business), e.g. the Nasdaq exchange (XNAS) has market operator The Nasdaq Stock Market LLC; its LEI from ISO 10383. First approved as `OPERATED_BY_LEGAL_ENTITY`; the operator asked for the actual meaning ("15 why operated by legal entity can we have the actual meaning") and chose this, 2026-10-07 09:28 ET |
| `VENUE_SEGMENT_OF` | `IS_SEGMENT_OF_EXCHANGE` (the operator rejected both first options, "Both don't make any sense make it better", then chose it: e.g. Nasdaq Global Select Market (XNGS) is a segment of the Nasdaq exchange (XNAS)) |

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
4. **`SUCCESSOR_ENTITY`** (named above): a new relationship type, the entity that ceased → the
   entity that took it over, with the effective date and basis. It is not a
   parent: the ceased entity's own parent links end on that date, and its
   children's links end unless a source restates them. GLEIF's successor LEI
   (with its entity status) fills it; SEC filings can later.

## Checklist

- [x] Ruling recorded, with the definitions shown to the operator 2026-10-07 08:36 ET
- [x] Each name reviewed against the source's own terms and approved one by one (table above) 2026-10-07 09:08 ET
- [x] Every other relationship name reviewed the same way and approved one by one (table above) 2026-10-07 09:24 ET
- [ ] `rules/merge/relationships.yaml` and `rules/context/definitions.yaml`: every approved name; the removed names gone; attributes: `basis`, `discretion`, `investment_discretion`, `voting_authority`, `percent`, capacities as approved
- [ ] `CONTEXT.md`: the glossary uses the approved names (Ownership Parent, Accounting Direct Parent, Reported and Calculated Ultimate Parent, MANAGES_FUND entries rewritten)
- [ ] GoF consult (relationships.py types and derivation, relationships.yaml, the relationship view)
- [ ] `rules/merge/relationships.yaml`: `IS_DIRECTLY_CONSOLIDATED_BY` for any legal kind (hierarchy, cycles invalid, one parent, derives the ultimate parent) and `IS_ULTIMATELY_CONSOLIDATED_BY` (stated or calculated); `ACCOUNTING_PARENT` and `REPORTED_ULTIMATE_PARENT` removed; `rules/context/definitions.yaml` and `CONTEXT.md` say the definitions above
- [ ] A relationship carries its `basis` (`stated` or `calculated`); `mdm.relationship_context` and `context relationship` show it
- [ ] The derivation writes `IS_ULTIMATELY_CONSOLIDATED_BY` with basis `calculated` (no more `CALCULATED_ULTIMATE_PARENT`)
- [ ] The new Mastering Policy digest, with a peel layer and the evidence (relationship tests on PG16), for the operator's approval
- [ ] `SUCCESSOR_ENTITY`: the type (ceased entity → successor, not a hierarchy parent), its definition; on its date the ceased entity's parent links end, and its children's links end unless restated
- [ ] Parent periods take a stated effective date when the source gives one (`valid_from_basis` / `valid_to_basis` stated), else first or last seen
- [ ] The calculated ultimate parent has periods: recomputed at every change in its chain, so `--as-of` answers any date
- [ ] GLEIF's `SuccessorEntity`, event type and effective date mapped to `SUCCESSOR_ENTITY` (Codex's path: handoff, or the operator's word)
- [ ] ~~Corporate action events in silver~~ deferred to [06](06-silver-writer.md): they are transaction data, written by the silver writer; a parent period cites its event once they exist (added 2026-10-07 08:38 ET)
- [ ] Review (Standards, Spec, GoF), PR, CI, merge on word
