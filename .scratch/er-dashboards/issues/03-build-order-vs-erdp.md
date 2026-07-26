# 03 — Build order vs ERDP readiness

Type: task  
Status: resolved  
Blocked by: 01, 02  

## Question

Given ERDP-03 (calendar) and ERDP-07 (EOD) are implemented, and ERDP-01/02/04 are not, what is the phase-1 **implementation** order for ER dashboards?

## Answer

**Ship P0 on gold + ERDP-03 + ERDP-07; stub Street panels.**

| Order | Deliverable | Why first |
|-------|-------------|-----------|
| P0a | ERD-2 Catalyst Board | Calendar product ready; high daily use |
| P0b | ERD-3 Valuation Explore + Thesis shell | EOD ready; reuses Company Details |
| P0c | ERD-1 Earnings Desk shell | GAAP + calendar; stubs for consensus/guidance/transcript |
| P0d | ERD-4 Value Explore recipe | EOD + factors |
| P1 | Fill ERDP-01/02/04 panels | After er-data-plane resumes |

**Empty-state rule:** never invent consensus/transcript; show “requires ERDP-0x”.

See [spec.md §12](../spec.md) and er-data-plane `HANDOFF.md`.
