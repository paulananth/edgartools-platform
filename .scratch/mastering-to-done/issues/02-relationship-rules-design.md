# Relationship rules design

Type: grilling (HITL)
Status: resolved
Blocked by: none

## Question

The relationship rules for Companies and People: platform validation 06, step 2 (`.scratch/platform-validation/issues/06-relationship-rules.md`, `research/06-relationship-inventory.md`).

Open points:
- The 72 GLEIF links that wait for their other end: are they open reviews, or quiet waits?
- Should link ends stop the closure at full GLEIF scale?
- Which Person link types come first: insider, officer, director, 10% owner.
- How each Person link type is keyed and given periods.
- What pairs with the Person feed 1 switch-on.

## Checklist

Status: claimed (Claude, branch `claude/mastering-02-relationship-rules`, 2026-10-02 11:05 ET).

- [x] D1. Scope of the first relationship rules document. Operator, 2026-10-02 11:08 ET: "GLEIF + Forms 3/4/5 (Recommended)".
- [x] D2. The GLEIF links waiting for their other end. Operator, 2026-10-02 11:10 ET: "Wait quietly (Recommended)".
- [x] D3. How a Forms 3/4/5 link builds history. Operator, 2026-10-02 11:12 ET: "Each filing a record (Recommended)".
- [x] D4. What ends an insider link: already decided in `docs/specs/person/consumer.md` ("What closes an interval"), so not asked again. 2026-10-02 11:14 ET
- [ ] ~~D5. Whether link ends stop the closure at full scale~~ deferred to ticket 06: an engine decision, settled by the full-scale measurement there, not asked
- [x] Write the decisions into `.scratch/platform-validation/issues/06-relationship-rules.md` step 2 and the inventory's open questions
- [x] Graduate the build work into tickets 13 (waiting links wait quietly) and 14 (the Person link engine). 2026-10-02 11:20 ET
- [ ] PR, CI green, merge on the operator's word

## Answer

The first relationship rules document covers two families:

| Family | Types | Ends matched by | Key | History | What ends it |
|---|---|---|---|---|---|
| Company → Company, GLEIF | `IS_DIRECTLY_CONSOLIDATED_BY`, `IS_ULTIMATELY_CONSOLIDATED_BY` (plus the calculated ultimate) | LEI to the Company's GLEIF Level 1 record | child, parent, kind (design 1) | GLEIF periods on the one link | only GLEIF's own statement: inactive, or a stated end (design 2) |
| Person → Company, Forms 3/4/5 | `EMPLOYED_BY` (director, officer), `CONTROLS` (10% owner) | owner CIK to Person; issuer CIK to Company (approved CIK rules) | Person, Company, capacity; the officer title is a dated detail | each filing, per reporting owner, is its own source record, and adds a dated sighting (D3) | a later filing from the same issuer that drops the capacity (observed end); a contradiction after a stated end goes to a steward; silence never ends it |

**A link whose other end is not yet an accepted entity waits quietly (D2).** It is set aside, not an open steward review. It is re-checked when that end is accepted, and each run reports how many links wait, with a readable list.

**Not in this document**, each waiting as a non-blocking unsupported type until its source or kind exists:
- trustee and attorney-in-fact;
- series LLC ("a series of");
- dba;
- ET AL;
- ownership parents (Exhibit 21, 13D/13G);
- GLEIF branches and funds;
- holdings (Person → Security);
- `MANAGES_FUND`.

The inventory's questions 3–10 move to those later feeds.

**Each relationship rule is a versioned rule in the Mastering Policy.** It is proven on a pinned cohort (links opened, closed, waiting and in conflict, plus a hand-checked sample), approved by the operator, and switched on with Person feed 1 (ticket 12).
