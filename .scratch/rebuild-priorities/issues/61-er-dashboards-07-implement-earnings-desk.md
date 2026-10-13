# 07 — Implement ERD-1 Earnings Desk shell

Priority: 61, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/er-dashboards/issues/07-implement-earnings-desk.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task  
Status: open  
Blocked by: 59, 60  

## Question / work

Implement Earnings Desk with pre/post toggle, GAAP flash, calendar header, actuals CSV export, and stubs for ERDP-01/02/04 per [spec.md §6](../../er-dashboards/spec.md).

### Acceptance

- [ ] Pre-print: calendar row + prior DERIVED
- [ ] Post-print: `EARNINGS_RELEASES` GAAP metrics when present
- [ ] Download CSV actuals plug table
- [ ] Explicit stub panels for consensus / guidance / transcript
- [ ] Explore-only EOD multiples strip optional
- [ ] Mode gating tests

### Depends on data plane (soft)

- Consensus/guidance/transcript panels remain stub until ERDP-01/02/04  
