# bookkeeping: Make the entrypoint executable

Type: task
Status: open
Priority: P1
Blocked by: 03, 21, 44
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [bookkeeping](../../../skills/bookkeeping/SKILL.md)
Step: 3 of 6
Skill dependencies: data-onboarding
Applicability: Every source's declared execution targets; honor the target's configured grain.

## Question

What is the shortest sufficient entrypoint for a reader to perform this phase correctly using existing supported commands?

## Scope and evidence

Keep the entrypoint focused on applicability, prerequisites, exact supported commands, expected outputs, next owner and stop conditions. Inputs: declared source targets, verified worker profiles, immutable run facts and captured-file references. Outputs: an executable run plan, verified step outcomes and recoverable execution state. Open optional references only when needed; do not move a hard stop out of the required reading path.

Check existing splits before proposing another move; line count alone is not a completion measure.

Start from skills/bookkeeping/SKILL.md: Required independence, Source registration, Grain, Validate, Recover. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make the entrypoint executable](./03-data-platform-entrypoint.md); [data-onboarding: Make the entrypoint executable](./21-data-onboarding-entrypoint.md); [bookkeeping: Reconcile shared rules](./44-bookkeeping-consistent-rules.md)

Priority rationale: Configured targets must execute with verified recovery.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Produce an entrypoint that consumes declared source targets, verified worker profiles, immutable run facts and captured-file references and yields an executable run plan, verified step outcomes and recoverable execution state.
- [ ] Verify referenced paths and supported commands; retain mandatory stops and discoverability of optional detail.
- [ ] Walk one applicable example to its handoff without loading unrelated references or repeating another skill's procedure.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
