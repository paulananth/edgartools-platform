# Create a platform AutoOntology setup skill

Type: task
Status: claimed

Add repository guidance to initialize and reset NVIDIA AutoOntology as a semantic layer above MDM, RDM and Silver. Keep all platform stores read-only and intact; cleanup is limited to the exact AutoOntology-owned deployment state.

## Checklist

- [x] Read the repository skill-writing and platform connection/catalog rules, plus NVIDIA's versioned setup and management guidance. 2026-11-14 10:04 ET
- [x] Add `skills/auto-ontology/SKILL.md` with preflight, scoped reset-and-init, MDM/RDM/Silver read-only source boundaries, data-sampling gates, and verification. 2026-11-14 10:04 ET
- [x] Add the skill to `skills/README.md`; confirm the bundle discovers all skill folders dynamically. 2026-11-14 10:04 ET
- [x] Run documentation checks: `tests/unit/test_profiling_genericity.py` and `tests/unit/test_guides_name_existing_paths.py`, 108 passed. 2026-11-14 10:04 ET
- [ ] Publish the committed change in a draft PR and mark ready only after current-head CI is green.
- [x] Learning → skill: `skills/auto-ontology/SKILL.md` now owns AutoOntology platform setup and reset guidance. 2026-11-14 10:04 ET
