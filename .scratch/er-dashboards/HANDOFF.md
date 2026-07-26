# Handoff: ER dashboards (design complete)

**Date:** 2026-07-25  
**Repo:** edgartools-platform  
**Workstream dir:** `.scratch/er-dashboards/`  
**Status:** Design destination reached. Implementation tickets **05–08 open**.

---

## Start here

1. Read [map.md](./map.md) and [spec.md](./spec.md)
2. Skill coverage: [assets/skill-dashboard-map.md](./assets/skill-dashboard-map.md)
3. Wireframes: [assets/wireframes.md](./assets/wireframes.md)
4. Mode rules: [assets/data-mode-matrix.md](./assets/data-mode-matrix.md)
5. Data readiness: `.scratch/er-data-plane/HANDOFF.md` (ERDP-03/07 done; 01/02/04 open)

---

## Frontier (first open unblocked implementation ticket)

| # | Ticket | Blocked by |
|---|--------|------------|
| **05** | Implement Catalyst Board | 03, 04 resolved → **unblocked** |
| 06 | Valuation Explore tab | unblocked |
| 07 | Earnings Desk | 05, 06 |
| 08 | Idea & Sector recipes | 04, 06 |

Suggested first build: **issue 05** (calendar UI is self-contained and ERDP-03 ready).

---

## Constraints (do not regress)

- ADR 0001 / ERDP-06: no prices or Street data in Agent View Decision Features
- C-06 style: do not rewrite financial-services ER skill bodies in this effort
- Empty states for missing ERDP-01/02/04 — never fabricate consensus/transcripts
- Prefer extend SiS app over a second production host

---

## Optional later

- Promote summary to `docs/er-dashboards.md` after first page ships
- financial-services skill docs: one-line “prefer platform Catalyst Board when available”
- Align coverage-matrix Partial→Covered when dashboard read paths exist
