# 06 — Implement ERD-3 Valuation Explore tab

Priority: 60, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/er-dashboards/issues/06-implement-research-valuation-tab.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task  
Status: open  
Blocked by: er-dashboards 03, er-dashboards 04  

## Question / work

Add **Valuation Explore** + **Thesis** panel shell to Company / Research Workspace per [spec.md §8](../../er-dashboards/spec.md).

### Acceptance

- [ ] Explore: CIK→ticker→EOD snapshot via ERDP-07 helpers (mock path in CI)
- [ ] EV / simple multiples using gold DERIVED + mcap
- [ ] Labels: `source_system=yahoo`, `grade=explore`
- [ ] Agent View: tab disabled with ADR explanation
- [ ] Thesis panel: session text fields + evidence chips from available Explore gold (no thesis SoR)

### Out of scope

- Full DCF Excel authoring  
- Street PT history  
