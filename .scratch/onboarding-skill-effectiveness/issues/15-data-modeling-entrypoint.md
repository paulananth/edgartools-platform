# data-modeling: Make the entrypoint executable

Type: task
Status: open
Blocked by: 14, 03
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-modeling](../../../skills/data-modeling/SKILL.md)
Step: 3 of 6
Applicability: Every new part whose class, identity, relationship or destination needs mapping.

## Question

What is the shortest sufficient entrypoint for a reader to perform this phase correctly using existing supported commands?

## Scope and evidence

Keep the entrypoint focused on applicability, prerequisites, exact supported commands, expected outputs, next owner and stop conditions. Inputs: profiling findings, CONTEXT.md, existing kind definitions and published reference sets. Outputs: a model decision per part with identity versus lookup choices and destination rationale. Open optional references only when needed; do not move a hard stop out of the required reading path.

Check existing splits before proposing another move; line count alone is not a completion measure.

Start from skills/data-modeling/SKILL.md: Decision rules, Workflow, Prove the model on the data before building. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-modeling: Reconcile shared rules](./14-data-modeling-consistent-rules.md); [data-platform: Make the entrypoint executable](./03-data-platform-entrypoint.md)

## Acceptance checklist

- [ ] Produce an entrypoint that consumes profiling findings, CONTEXT.md, existing kind definitions and published reference sets and yields a model decision per part with identity versus lookup choices and destination rationale.
- [ ] Verify referenced paths and supported commands; retain mandatory stops and discoverability of optional detail.
- [ ] Walk one applicable example to its handoff without loading unrelated references or repeating another skill's procedure.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
