# data-platform: Define one responsibility

Type: task
Status: open
Blocked by: none
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-platform](../../../skills/data-platform/SKILL.md)
Step: 1 of 6
Applicability: Every source: route the work and discover configured connections.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Route from current source readiness to the next owning skill; own setup and connection discovery, not each downstream procedure.

Inventory existing instructions against the neighboring owners: data-profiling, data-onboarding, refining-rules or data-operations. Reconcile the current index and references before moving any text.

Start from skills/data-platform/SKILL.md: Source readiness, The flow, Connection URLs and environment. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

None. This is the first frontier ticket.

## Acceptance checklist

- [ ] List decisions, inputs and outputs owned here using current repository evidence.
- [ ] Assign each overlapping responsibility one authoritative owner and a named handoff.
- [ ] Demonstrate the boundary on a new captured source, an already configured source and a restart after a completed phase; link retained work rather than duplicating it.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
