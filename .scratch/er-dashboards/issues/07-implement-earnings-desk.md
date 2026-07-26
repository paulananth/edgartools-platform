# 07 — Implement ERD-1 Earnings Desk shell

Type: task  
Status: open  
Blocked by: 05, 06  

## Question / work

Implement Earnings Desk with pre/post toggle, GAAP flash, calendar header, actuals CSV export, and stubs for ERDP-01/02/04 per [spec.md §6](../spec.md).

### Acceptance

- [ ] Pre-print: calendar row + prior DERIVED
- [ ] Post-print: `EARNINGS_RELEASES` GAAP metrics when present
- [ ] Download CSV actuals plug table
- [ ] Explicit stub panels for consensus / guidance / transcript
- [ ] Explore-only EOD multiples strip optional
- [ ] Mode gating tests

### Depends on data plane (soft)

- Consensus/guidance/transcript panels remain stub until ERDP-01/02/04  
