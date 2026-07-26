# 06 — Implement ERD-3 Valuation Explore tab

Type: task  
Status: open  
Blocked by: 03, 04  

## Question / work

Add **Valuation Explore** + **Thesis** panel shell to Company / Research Workspace per [spec.md §8](../spec.md).

### Acceptance

- [ ] Explore: CIK→ticker→EOD snapshot via ERDP-07 helpers (mock path in CI)
- [ ] EV / simple multiples using gold DERIVED + mcap
- [ ] Labels: `source_system=yahoo`, `grade=explore`
- [ ] Agent View: tab disabled with ADR explanation
- [ ] Thesis panel: session text fields + evidence chips from available Explore gold (no thesis SoR)

### Out of scope

- Full DCF Excel authoring  
- Street PT history  
