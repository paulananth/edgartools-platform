# 05 — Implement ERD-2 Catalyst Board (SiS)

Type: task  
Status: open  
Blocked by: 03, 04  

## Question / work

Implement Catalyst Board page in Streamlit-in-Snowflake per [spec.md §7](../spec.md) and [wireframes.md](../assets/wireframes.md).

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
