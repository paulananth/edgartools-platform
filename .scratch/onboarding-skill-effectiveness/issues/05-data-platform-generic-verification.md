# data-platform: Specify generic verification

Type: task
Status: open
Priority: P0
Blocked by: 04
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-platform](../../../skills/data-platform/SKILL.md)
Step: 5 of 6
Skill dependencies: none
Applicability: Every source: route the work and discover configured connections.

## Question

Which complete behavioral scenarios prove this skill's claims, using shared tooling and source-supplied fixtures rather than copied source-specific logic?

## Scope and evidence

Propose Given–When–Then scenarios before writing test code and obtain the operator's required scenario approval. Start with: a new captured source, an already configured source and a restart after a completed phase.

Required observable proof: route a new source, a changed source and an interrupted load to their distinct owners without redoing completed phases. Reuse existing generic workers, fixtures and harnesses; configuration and invented input data supply source differences. If tooling cannot express a behavior, link a separate capability-gap ticket rather than adding source-specific runtime code here.

Start from skills/data-platform/SKILL.md: Source readiness, The flow, Connection URLs and environment. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make progress resumable](./04-data-platform-resume.md)

Priority rationale: Shared routing and rule conventions unblock every track.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Record distinct Given–When–Then scenarios and obtain the required scenario approval before test implementation.
- [ ] Use the existing generic path to route a new source, a changed source and an interrupted load to their distinct owners without redoing completed phases.
- [ ] Record stored outcomes, affected checks and limitations; no mock-call-only, static-text or tautological proof.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
