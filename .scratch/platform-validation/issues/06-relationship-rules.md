# Relationship rules for Companies and People

Type: task (wayfinding first, then onboarding)
Status: in progress (Claude, branch `claude/relationship-rules-inventory`)

## Operator rulings

- "Yes I think there has to be relationship along with mdm it can not be
  separated" (2026-10-01, on a trustee filer).
- "Ok name has the relationship as well" (2026-10-01, on "a series of").
- "we need to build rules for relationships for both companies and people"
  (2026-10-01, asked whether Person feed 1 may go live without links). So
  Person feed 1 is not switched on until relationship rules exist.
- "Yes please" to step 1, the inventory (2026-10-01).
- "Yes" (2026-10-01 19:05 ET): start with the GLEIF accounting parent for
  Companies, from the files already local. Forms 3/4/5 capture and reader is a
  separate ticket that waits for the operator's permission to request from SEC
  and to write code.
- Design 1, "Yes" (2026-10-01): a Company accounting-parent relationship is
  identified by child Company, parent Company and kind of parent (direct or
  ultimate). Dates and status are history on that one relationship; a new
  parent closes the old link and opens a new one.
- Design 2, "Yes" (2026-10-01): a parent link ends only on GLEIF's own
  statement (status inactive, or a stated end date). Absence from a later
  file never closes it; it stays open, flagged as not seen recently.

## Plan

1. Inventory, no code: every relationship type, the sources that state it,
   how each end is identified, and what exists today.
2. Design the relationship rules document, approved and switched on like
   identity rules.
3. Onboard the GLEIF accounting parent first (06a). Then a person's role at
   a company from Forms 3/4/5 (06b, waiting on SEC-request and code
   permission). GLEIF branch waits for a Branch kind (inventory).
4. Switch on together: Person feed 1 and both relationship feeds.

## Checklist

- [x] 1. Inventory written (2026-10-01 19:00 ET, research agent, read-only; key claims spot-checked: parsers deleted in #764, `gleif.relationships.v1` absent from Company sources):
  `.scratch/platform-validation/research/06-relationship-inventory.md`
- [ ] 1. Inventory reviewed with the operator
- [ ] 2. Relationship rules design: the operator's answers to the inventory's
  questions, then the design
- [ ] 06a: GLEIF accounting parent (direct, with the reported ultimate)
- [ ] 06b: Forms 3/4/5 capture and reader. Not started: needs the operator's
  permission for SEC requests and code
- [ ] 3. First relationship feeds onboarded: tickets after the design
- [ ] 4. Switch-on of Person feed 1 with the relationship feeds
- [ ] Map entry for slice 6 in `map.md`
- [ ] PR; CI green; merge on the operator's word
