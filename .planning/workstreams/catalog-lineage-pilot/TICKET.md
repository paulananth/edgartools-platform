# One pipeline lineage pilot

Scope: invented metadata only, isolated catalog services; no source records or
pipeline runs. User review precedes expansion. No computer use.

- [x] Build one configuration-driven example with stages, field mappings and separate control interactions. — 2026-10-30 15:02 ET: example.json drives both outputs; configuration validation passed.
- [x] Test native pipeline association, task dependencies, field lineage, drift detection and repeat publication through the API. — 2026-10-30 15:02 ET: receipt.json records API outcomes for 3 datasets, 2 stages, 2 field links and 1 pipeline; negative-mapping and repeat checks passed.
- [x] Provide a bird's-eye review page with expandable detail; distinguish preview from native catalog capability. — 2026-10-30 15:02 ET: HTML structural checks passed and Lavish review opened; native UI lanes remain explicitly unsupported by this pilot.
- [x] Publish the pilot and evidence in a PR; ask the operator to check one example before expansion. — 2026-10-30 15:03 ET: draft PR #1252 contains the pilot and receipt; the Lavish review link was sent to the operator.
- [ ] Final-head CI and PR readiness after operator review.
- [ ] Operator review of the example.
- [x] Learning → skill: none in this bounded pilot; existing catalog guidance already requires invented API proof and explicit capability gaps. — 2026-10-30 15:02 ET: README records the native-versus-preview boundary; any production design lesson follows operator review.

Design review: existing catalog.py already separates projection and API transport.
Its recent changes add metadata coverage, not repeated polymorphic behavior.
Keep that boundary; no GoF hierarchy is warranted for a bounded prototype.
The pilot is not wired into the production publisher.
