# 07 — Implement ERD-1 Earnings Desk shell

Priority: 61, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/er-dashboards/issues/07-implement-earnings-desk.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task  
Status: closed (2026-10-18 12:25 ET, operator: "Close all, re-raise later (Recommended)"): written for the retired Snowflake gold layer; product value on the rebuild comes from the financials (33–48), then new tickets written against silver and the context views
Blocked by: 59, 60  

## Question / work

Implement Earnings Desk with pre/post toggle, GAAP flash, calendar header, actuals CSV export, and stubs for ERDP-01/02/04 per [spec.md §6](../../er-dashboards/spec.md).

### Acceptance

- [ ] ~~Pre-print: calendar row + prior DERIVED~~ closed with the ticket (2026-10-18 12:25 ET)
- [ ] ~~Post-print: `EARNINGS_RELEASES` GAAP metrics when present~~ closed with the ticket (2026-10-18 12:25 ET)
- [ ] ~~Download CSV actuals plug table~~ closed with the ticket (2026-10-18 12:25 ET)
- [ ] ~~Explicit stub panels for consensus / guidance / transcript~~ closed with the ticket (2026-10-18 12:25 ET)
- [ ] ~~Explore-only EOD multiples strip optional~~ closed with the ticket (2026-10-18 12:25 ET)
- [ ] ~~Mode gating tests~~ closed with the ticket (2026-10-18 12:25 ET)

### Depends on data plane (soft)

- Consensus/guidance/transcript panels remain stub until ERDP-01/02/04  
