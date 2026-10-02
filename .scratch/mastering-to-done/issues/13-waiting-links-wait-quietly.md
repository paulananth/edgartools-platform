# Waiting links wait quietly

Type: task (code)
Status: resolved (#793)
Blocked by: 02

## Question

Ticket 02, D2: a link whose other end is not an accepted entity is set aside, not an open review. Today the engine opens `unresolved_endpoint` reviews (`edgar_warehouse/mdm/clean/relationships.py:116`). The change:
- hold such a link as a set-aside record that names the missing end;
- re-check it when that end is accepted;
- count and list waiting links in the run report.

Steps: GoF consult first, then tests on PostgreSQL 16. In the GLEIF test run, the 72 waiting links must leave the open reviews and appear in the waiting count.

## Checklist

Copied from the #793 description after #786 created this file.

- [x] GoF consult before the code: no new structure. 2026-10-02 by 11:58 ET
- [x] Tests written first, both failing before the change. 2026-10-02 by 11:58 ET
- [x] The change, plus the review fixes. 2026-10-02 12:08 ET
  - **Spec:** unaccepted ends wait too; the missing end is named; the list is added; the count covers all current waiting links.
  - **Standards:** retired links are excluded from the count; the flag is renamed; the disposition is a helper.
  - **GoF:** leave it.
- [x] Tests: integration (relationship identity, run, review scope, fresh mastering and the clean MDM core), 63 passed on PostgreSQL 16; testmon over `tests/mdm` and `tests/unit` passed. 2026-10-02 12:08 ET
- [ ] ~~The GLEIF run's 72 waiting links leave the open reviews~~ deferred to ticket 06: it reruns GLEIF on a fresh store
- [x] CI green; merge on the operator's word: #793, merged 2026-10-02 12:21 ET (operator, 2026-10-02: "yes merge one by one and continue implementing ticket 14")
