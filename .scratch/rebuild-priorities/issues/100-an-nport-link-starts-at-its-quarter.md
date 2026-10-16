# An N-PORT link starts at its quarter's data set

Priority: 100, tier 1, blocks ticket 22's resolution. Map: [Rebuild priorities](../map.md).

Type: task (configuration). Status: configured; Proving Run 3 next (ticket 22's branch, since the link it dates is there). Blocked by: none. Blocks: 22 (ISSUED_BY by issuer LEI).

## Why

Ticket 22's Proving Run 2 (2026-10-16): 177,856 ISSUED_BY links reached both ends and went to review as `unknown_relationship_start`. A link with no stated start starts when it was first seen, the publication's effective time (`edgar_warehouse/mdm/clean/relationships.py:249-262`); the N-PORT Security publication states none (`effective_time: unknown`), and the holdings carry no date of their own.

## Proposed change

The N-PORT Security publication states the quarter's data set period as its effective time: the run supplies the quarter's period in the reading's context, the combine passes it as a column, and `mdm.prepare` dates each publication by it (`effective_column`). Each link then starts, as observed, at the first quarter that names it. If the configured grammar cannot carry it, stop and write the code ticket.

## Checklist

- [x] The run names the quarter: the reading's context gains `period` (an instant with its zone); the link itself cannot state an observed start (a contract link has no basis), so the publication states it 2026-10-16 14:48 ET
- [x] Configuration only: `source.yaml` reads `period` from context into both holding tables; `reduce.yaml` keeps it in the CUSIP and ISIN keys (constant per quarter), so each Security row carries it; `mdm.prepare` dates each publication by it (`effective_column: period`); the contract states its effective time. 2026-10-16 14:48 ET
- [x] Check on three invented holdings through the real chain and the Merge Stage on PG16 (`.scratch/onboarding/sec.nport/link_start_check.py`): every prepared batch dated by its quarter; the ISSUED_BY link resolves, starting at the quarter, `observed`; no review. Without `effective_column` it reopens `unknown_relationship_start` (Proving Run 2's failure) 2026-10-16 14:48 ET
- [ ] ~~A second quarter keeps the first start~~ deferred to ticket 101 (A second N-PORT quarter is a new revision): each quarter's records are revision 1 of the same subjects, refused today
- [x] On the real quarter (ticket 22's Companies-only proof): every prepared batch dated 2026-06-30; 41,360 links resolve with their issuer's Company, none lacks a start 2026-10-16 15:20 ET
- [ ] PR, CI green, merge on the operator's word
- [ ] Learning → skill
