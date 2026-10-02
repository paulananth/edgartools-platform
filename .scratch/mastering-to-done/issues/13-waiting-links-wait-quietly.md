# Waiting links wait quietly

Type: task (code)
Status: open
Blocked by: 02

## Question

Ticket 02, D2: a link whose other end is not an accepted entity is set aside, not an open review. Today the engine opens `unresolved_endpoint` reviews (`edgar_warehouse/mdm/clean/relationships.py:116`). The change:
- hold such a link as a set-aside record that names the missing end;
- re-check it when that end is accepted;
- count and list waiting links in the run report.

Steps: GoF consult first, then tests on PostgreSQL 16. In the GLEIF test run, the 72 waiting links must leave the open reviews and appear in the waiting count.
