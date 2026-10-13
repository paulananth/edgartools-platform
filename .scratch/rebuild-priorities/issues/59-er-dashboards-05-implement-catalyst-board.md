# 05 — Implement ERD-2 Catalyst Board (SiS)

Priority: 59, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/er-dashboards/issues/05-implement-catalyst-board.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task  
Status: open  
Blocked by: er-dashboards 03, er-dashboards 04  

## Question / work

Implement Catalyst Board page in Streamlit-in-Snowflake per [spec.md §7](../../er-dashboards/spec.md) and [wireframes.md](../../er-dashboards/assets/wireframes.md).

### Acceptance

- [ ] Explore-only calendar query against `EARNINGS_CALENDAR` (or empty state if table missing)
- [ ] Horizon filter 7/14/30d; session filter; tracked-universe or paste list
- [ ] Table columns: date, session, ticker, CIK, FY/FQ, status, source
- [ ] Open Earnings Desk / Company deep-link with CIK in session state
- [ ] Agent View shows blocked panel + switch hint (no free gold)
- [ ] Unit/architecture tests for mode gating of calendar object

### Out of scope

- Macro/conference calendars  
- Rewriting ER skill markdown  
