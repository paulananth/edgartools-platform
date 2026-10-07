# 04c GLEIF's successor entity, read from its lists

Type: task. Phase: A. Blocked by: 04b. Map: [map](../map.md). Plan: [plan](../plan.md).

## Why

Ticket 04b declared `SUCCESSOR_ENTITY` (GLEIF's term) and made a succession
end the ceased entity's parent links on its date. No source fills it yet.
GLEIF's Level 1 file does, but its data sits in lists, which the contract
language cannot read: a path reads one value.

## Evidence (local GLEIF Golden Copy, 2026-09-11; full scan, 262 s)

Of 3,428,477 Level 1 records:

- 51,913 have `Entity.SuccessorEntity`, always a list. 34,612 name the
  successor's LEI (`SuccessorLEI`); 17,301 name it only
  (`SuccessorEntityName`), which can make no link. 580 list several
  successors (a demerger or breakup).
- `Entity.EntityExpirationDate` and `EntityExpirationReason` are empty on every
  record.
- The effective date and event type are in `Entity.LegalEntityEvents.LegalEntityEvent`
  (a list): the event whose `AffectedFields.AffectedField` names the
  successor's LEI. On records with a successor: COMPLETED
  `MERGERS_AND_ACQUISITIONS` 38,277, `ABSORPTION` 6,420, `DEMERGER` 418,
  `BREAKUP` 135; IN_PROGRESS `MERGERS_AND_ACQUISITIONS` 585, `ABSORPTION` 416;
  WITHDRAWN_CANCELLED `MERGERS_AND_ACQUISITIONS` 51. Each event has
  `@event_status`, `LegalEntityEventType`, `LegalEntityEventEffectiveDate`,
  `LegalEntityEventRecordedDate`.

## Ruling (operator, 2026-10-07)

- "It's configuration why are you saying code": the mapping is configuration
  (`rules/sources/gleif/source.yaml`), done by Claude, not a handoff. Then
  "Yes" to doing it.
- The scan showed the language cannot read lists. Two generic additions were
  proposed: `each` (one link per item of a list) and a lookup of the matching
  item of another list (the completed event naming the successor, for a
  stated date and the event type). The operator: "Approved" (2026-10-07 13:07 ET).

## Checklist

- [x] Scan the Golden Copy for the successor fields (evidence above) 2026-10-07 13:05 ET
- [x] GoF consult on the relationship mapping in `adapters.normalize`: no refactor; put `each`/`find` into what the paths read (a scope per link, `_scopes`), not into each read; the loop body becomes `_link`; refuse a name that hides a record field 2026-10-07 13:21 ET
- [x] Contract language: `each` (one link per list item, paths `item.`…) and `find` (the first item of another list whose fields match; a path through a nested list matches any element), in `adapters.normalize`; REFERENCE.md says it; the Mapping Document lists the paths (catalog already says a source carries relationships) (tests/mdm/test_clean_relationship_lists.py; a mapping without them keeps its assertion id, test_clean_link_start) 2026-10-07 13:21 ET
- [x] `rules/sources/gleif/source.yaml`, `gleif.level1.v1`: `SUCCESSOR_ENTITY` per successor LEI, `valid_from` the completed event's effective date, `source_event_type`, `source_event_status` (tests/mdm/test_clean_gleif_source.py) 2026-10-07 13:21 ET
- [x] Test on captured records: every one of the 51,913 Golden Copy records naming a successor, through the real GLEIF reader (`.scratch/profiling/trials/gleif-successor/RESULT.json`, 374 s): 43,520 read, 8,393 wait as other kinds (8,318 funds, branches and other categories; 75 invalid LEI checksums); 27,667 links, exactly one per successor LEI on every record read; 22,070 dated by a completed event (MERGERS_AND_ACQUISITIONS 19,247, ABSORPTION 2,214, DEMERGER 275, CHANGE_LEGAL_FORM 150, BREAKUP 89, DISSOLUTION 75, others 20), 5,597 with no completed event naming the successor (start when first seen); successors named only make none 2026-10-07 13:21 ET
- [ ] The GLEIF Level 1 contract digest c7655ed6… (peel back to 74b8b1f4…), for the operator's approval
- [x] Mapping Document regenerated (`rules mapdoc write --only gleif`), `rules mapdoc check` passes 2026-10-07 13:21 ET
- [x] PG16: a successor link ends the ceased entity's parent link through the full path, and its calculated ultimate parent, on the event date, citing the succession (tests/integration/test_fresh_mastering_postgres.py; 1,222 unit and MDM tests and the GLEIF integration tests pass; the bundle tests need cargo, run by CI) 2026-10-07 13:21 ET
- [ ] Review (Standards, Spec, GoF), PR, CI, merge on word
