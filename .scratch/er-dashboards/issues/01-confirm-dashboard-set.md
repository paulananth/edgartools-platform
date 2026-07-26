# 01 — Confirm dashboard set vs skill map

Type: grilling  
Status: resolved  
Blocked by:  

## Question

How many ER dashboards should phase-1 design specify — one-per-skill (9), a thin extension of the existing 3 audit dashboards only, or a mid-size skill-grouped set?

## Answer

**Mid-size skill-grouped set: four primary dashboards + one embedded thesis panel.**

| ID | Name | Rationale |
|----|------|-----------|
| ERD-1 | Earnings Desk | Collapses preview + analysis + model actuals + flash into one earnings cycle |
| ERD-2 | Catalyst Board | Calendar-first desk board (not buried in company page) |
| ERD-3 | Research Workspace | Company 360 + ER valuation/thesis tabs — initiation home |
| ERD-4 | Idea & Sector Screen | Screener extended for idea-generation + sector multiples |
| ERD-5 | Thesis panel | Embedded in ERD-3 only — no fifth top-level app |

**Rejected:** nine separate apps (nav bloat, duplicate identity chrome).  
**Rejected:** only extend existing three without earnings/catalyst surfaces (skills’ highest-frequency paths stay underserved).

See [spec.md §4](../spec.md) and [skill-dashboard-map.md](../assets/skill-dashboard-map.md).
