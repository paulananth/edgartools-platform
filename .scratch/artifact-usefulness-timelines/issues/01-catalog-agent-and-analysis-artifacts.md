# Catalog agent-grade vs analysis artifacts

Type: research
Status: resolved
Blocked by: none
Blocks: 02, 03, 04, 05, 06, 07

## Question

What distinct **artifact / form families** feed (a) the Agent Decision Surface
and (b) investment analysis features or Explore — and which bulk-load path owns
each (relationship freeze, companyfacts/gold, ownership, ADV, etc.)?

## Exit criteria

- Table of artifact families with owner pipeline and agent vs Explore role.
- Explicit list of families that must **not** be mixed into Ticket 20
  relationship freeze denominators (e.g. financial features).
- Pointers into repo docs/code for each family.

## Answer

Twelve artifact families were cataloged. Agent Decision Surface consumption
splits cleanly: **relationship edges** in Decision Graph Bundles come from 13F
(`INSTITUTIONAL_HOLDS`), proxy + Item 5.02 8-K (`EMPLOYED_BY`), Form 3/4/5
(`IS_INSIDER` / holds), plus separate ADV / parent / auditor paths; **As-Of
Decision Features** and the Subject Feature Screen come from **companyfacts →
silver/gold**, not from multi-year 13F/8-K bulk-load. Ticket 20’s freeze inventory
today is only proxy + Item 5.02 8-K + 13F (`relationship_bulk_load.py`); it must
not use financial feature history, earnings-only 8-Ks, ADV/parent/auditor
inventories, or pre-XML 13F as freeze denominators. Full tables, windows, and
code pointers: [research/01-artifact-catalog.md](../research/01-artifact-catalog.md).
