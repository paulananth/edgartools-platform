# An N-PORT link starts at its quarter's data set

Priority: 100, tier 1, blocks ticket 22's resolution. Map: [Rebuild priorities](../map.md).

Type: task (configuration). Status: open. Blocked by: none. Blocks: 22 (ISSUED_BY by issuer LEI).

## Why

Ticket 22's Proving Run 2 (2026-10-16): 177,856 ISSUED_BY links reached both ends and went to review as `unknown_relationship_start`. A link with no stated start starts when it was first seen, the publication's effective time (`edgar_warehouse/mdm/clean/relationships.py:249-262`); the N-PORT Security publication states none (`effective_time: unknown`), and the holdings carry no date of their own.

## Proposed change

The N-PORT Security publication states the quarter's data set period as its effective time: the run supplies the quarter's period in the reading's context, the combine passes it as a column, and `mdm.prepare` dates each publication by it (`effective_column`). Each link then starts, as observed, at the first quarter that names it. If the configured grammar cannot carry it, stop and write the code ticket.

## Checklist

- [ ] Confirm the period is in the quarter's data set (file and submission table) and how the run names it
- [ ] Configuration: context value, combine column, `effective_column`; source contract `effective_time` stated
- [ ] Test run: every prepared batch dated by its quarter; Proving Run 3 (ticket 22): ISSUED_BY resolved
- [ ] PR, CI green, merge on the operator's word
- [ ] Learning → skill
