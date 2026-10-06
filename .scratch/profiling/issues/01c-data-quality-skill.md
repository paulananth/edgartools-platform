# 01c data-quality skill

Type: task. Phase: A. Blocked by: 01b. Map: [map](../map.md). Plan: [plan](../plan.md).

## Checklist

- [ ] GoF consult
- [ ] skills/data-quality/ extracted from onboarding quality + refining change-quality
- [ ] Invalid-row marking with evidence-backed fixes
- [ ] Callers rewired (guard first)
- [ ] Both trials' defects become loadable checks
- [ ] Profiling's quality items carry rows and masked examples (findings §3 schema), moved here from 01b (added 2026-10-05 20:02 ET)
- [ ] Each invalid hierarchy row marked (count and masked examples in findings, full key list in a sidecar), with a check and an evidence-backed fix or "needs steward", moved here from 01b (added 2026-10-05 20:02 ET)
- [ ] Verify rr invalid-row counts (3,194 for one relationship type with holds 1.0: cycles or an artefact) before building on them (added 2026-10-05 20:02 ET)
- [ ] New code values in compare (moved here from 01b; distribution drift stays with refining-rules) (added 2026-10-05 20:02 ET)
- [ ] Each defect maps to an existing check or fix, or becomes "new code: ticket"; the engine's quality code is not edited (added 2026-10-05 20:02 ET)
- [ ] Trial checks proven: engine check_quality loads them, quality.apply counts equal profiling's counts, one planted record per check (added 2026-10-05 20:02 ET)
- [ ] Genericity lint covers skills/data-quality; doctor 0 unresolved; rules skill command test passes (added 2026-10-05 20:02 ET)
- [ ] Review, PR, CI, merge on word
