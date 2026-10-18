# 05 — Implement ERD-2 Catalyst Board (SiS)

Priority: 59, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/er-dashboards/issues/05-implement-catalyst-board.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task  
Status: closed (2026-10-18 12:25 ET, operator: "Close all, re-raise later (Recommended)"): written for the retired Snowflake gold layer; product value on the rebuild comes from the financials (33–48), then new tickets written against silver and the context views
Blocked by: er-dashboards 03, er-dashboards 04  

## Question / work

Implement Catalyst Board page in Streamlit-in-Snowflake per [spec.md §7](../../er-dashboards/spec.md) and [wireframes.md](../../er-dashboards/assets/wireframes.md).

### Acceptance

- [ ] ~~Explore-only calendar query against `EARNINGS_CALENDAR` (or empty state if table missing)~~ closed with the ticket (2026-10-18 12:25 ET)
- [ ] ~~Horizon filter 7/14/30d; session filter; tracked-universe or paste list~~ closed with the ticket (2026-10-18 12:25 ET)
- [ ] ~~Table columns: date, session, ticker, CIK, FY/FQ, status, source~~ closed with the ticket (2026-10-18 12:25 ET)
- [ ] ~~Open Earnings Desk / Company deep-link with CIK in session state~~ closed with the ticket (2026-10-18 12:25 ET)
- [ ] ~~Agent View shows blocked panel + switch hint (no free gold)~~ closed with the ticket (2026-10-18 12:25 ET)
- [ ] ~~Unit/architecture tests for mode gating of calendar object~~ closed with the ticket (2026-10-18 12:25 ET)

### Out of scope

- Macro/conference calendars  
- Rewriting ER skill markdown  
