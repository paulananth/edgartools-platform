# An N-PORT link starts at its quarter's data set

Priority: 100, tier 1, blocks ticket 22's resolution. Map: [Rebuild priorities](../map.md).

Type: task (configuration). Status: done, merged with ticket 22 (#1022, 2026-10-16 18:27 ET). Blocked by: none. Blocks: 22 (ISSUED_BY by issuer LEI).

## Why

Ticket 22's Proving Run 2 (2026-10-16): 177,856 ISSUED_BY links reached both ends and went to review as `unknown_relationship_start`. A link with no stated start starts when it was first seen, the publication's effective time (`edgar_warehouse/mdm/clean/relationships.py:249-262`); the N-PORT Security publication states none (`effective_time: unknown`), and the holdings carry no date of their own.

## Proposed change

The N-PORT Security publication states the quarter's data set period as its effective time: the run supplies the quarter's period in the reading's context, the combine passes it as a column, and `mdm.prepare` dates each publication by it (`effective_column`). Each link then starts, as observed, at the first quarter that names it. If the configured grammar cannot carry it, stop and write the code ticket.

## Checklist

- [x] The run names the quarter: the reading's context gains `period` (an instant with its zone); the link itself cannot state an observed start (a contract link has no basis), so the publication states it 2026-10-16 14:48 ET
- [x] Configuration only: `source.yaml` reads `period` from context into both holding tables; `reduce.yaml` keeps it in the CUSIP and ISIN keys (constant per quarter), so each Security row carries it; `mdm.prepare` dates each publication by it (`effective_column: period`); the contract states its effective time. 2026-10-16 14:48 ET
- [x] Check on three invented holdings through the real chain and the Merge Stage on PG16 (`tests/integration/test_nport_link_start.py`, in CI): every prepared batch dated by its quarter; the ISSUED_BY link resolves, starting at the quarter, `observed`; no review. Without `effective_column` it reopens `unknown_relationship_start` (Proving Run 2's failure) 2026-10-16 14:48 ET
- [ ] ~~A second quarter keeps the first start~~ deferred to ticket 101 (A second N-PORT quarter is a new revision): each quarter's records are revision 1 of the same subjects, refused today
- [x] On the real quarter (ticket 22's Companies-only proof): every prepared batch dated 2026-06-30; 41,360 links would resolve with their issuer's Company (counted, not loaded) 2026-10-16 15:20 ET
- [x] Noted: the ISIN contract's publications are dated the same way (`period` is on both holding tables; its record key stays the ISIN, and it has no links yet: ticket 102) 2026-10-16 17:53 ET
- [x] Noted: `period` is a declared context field, so a holdings reading without it is refused (`invalid_context`); the earlier scratch runs (`security_test_run.py`, `security_figi_read.py`, `issuer_proving_run*.py`) need `period` to run again 2026-10-16 17:53 ET
- [ ] The N-PORT run wiring passes `period` in the holdings reading's context and `effective_column: period` to `mdm.prepare`: no platform command builds the N-PORT run yet; recorded on ticket 79 (its run wiring part)
- [x] In ticket 22's PR #1022, merged by the operator 2026-10-16 18:27 ET
- [x] Learning → skill: data-onboarding "Count the links MDM accepts" (#1018); a link's observed start comes from its publication's effective time 2026-10-16 17:53 ET
- [ ] ~~The N-PORT run wiring passes `period` in the holdings reading's context and `effective_column: period` to `mdm.prepare`~~ superseded by ticket 113 (operator, 2026-10-19: the quarter "if at all it should be captured in silver not on mdm"; an ISSUED_BY link "if issued by already exist do not overight if not use the filing date or quarter date or inception date")
