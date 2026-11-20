# data-operations: Specify generic verification

Type: task
Status: open
Blocked by: 58, 05
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-operations](../../../skills/data-operations/SKILL.md)
Step: 5 of 6
Applicability: Every local source qualification and operational load; hosted actions require applicable authorization.

## Question

Which complete behavioral scenarios prove this skill's claims, using shared tooling and source-supplied fixtures rather than copied source-specific logic?

## Scope and evidence

Propose Given–When–Then scenarios before writing test code and obtain the operator's required scenario approval. Start with: a first local load, unchanged replay, a missing capture receipt and a recoverable failed step.

Required observable proof: load into disposable PostgreSQL through the supported command, reconcile every input disposition and verify a no-op replay without stale-store false positives. Reuse existing generic workers, fixtures and harnesses; configuration and invented input data supply source differences. If tooling cannot express a behavior, link a separate capability-gap ticket rather than adding source-specific runtime code here.

Start from skills/data-operations/SKILL.md: Start with live state, Install and enable one source, Load a capture, Operate the recurring loop. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-operations: Make progress resumable](./58-data-operations-resume.md); [data-platform: Specify generic verification](./05-data-platform-generic-verification.md)

## Acceptance checklist

- [ ] Record distinct Given–When–Then scenarios and obtain the required scenario approval before test implementation.
- [ ] Use the existing generic path to load into disposable PostgreSQL through the supported command, reconcile every input disposition and verify a no-op replay without stale-store false positives.
- [ ] Record stored outcomes, affected checks and limitations; no mock-call-only, static-text or tautological proof.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
