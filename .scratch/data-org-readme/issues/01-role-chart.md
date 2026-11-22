# Data organization and role skills in README

Status: resolved

- [x] Check maintained skills and scope boundaries: inspected the maintained lifecycle role map and relevant specialist guides. 2026-11-21 19:04 ET
- [x] Create an Archify organization chart and README role matrix: all six roles, three functions and skill availability/gaps; illustrative organization, with paired roles as peers. 2026-11-21 19:04 ET
- [x] Validate documentation and diagram: 145 documentation checks passed; Archify validation, provenance and automated browser gates passed; canonical light SVG exported. 2026-11-21 19:04 ET
- [x] Review Standards, Spec and GoF: three independent reviewers found no actionable findings. 2026-11-21 19:04 ET
- [x] Learning → skill: none; reuse the maintained lifecycle role map. 2026-11-21 19:04 ET

## Answer

The root README now explains the dual-role lifecycle and links to an Archify
organization chart with an SVG preview and reproducible JSON candidate under
`docs/diagrams/data-organization/`. The skill mapping is pinned to the maintained
role map at `a3d2a6173dc96d60875b8d20a0773bb4f76c0645`.

The reference organization is illustrative, not staffed reporting lines.
Available guides are distinguished from deployed services. The analyst route
is scoped, BI lacks a generic dashboard builder, and no end-to-end production
AI/ML workflow is maintained. Unsourced job-listing counts and percentages from
the supplied text were omitted. Existing specialist guides remain authoritative;
this documentation does not introduce roles with new approval powers.

## Standards

No blocking findings. Existing skill owners are linked; capability limitations
remain explicit. No production code or new tests were added.

## Spec

All six requested roles and lifecycle stages are covered, with skills and gaps.

## GoF

Leave the design as it is; no production-code refactor is justified for this
documentation change.
