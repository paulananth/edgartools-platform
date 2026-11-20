# change-journal: Make the entrypoint executable

Type: task
Status: open
Priority: P1
Blocked by: 03, 45, 50
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [change-journal](../../../skills/change-journal/SKILL.md)
Step: 3 of 6
Skill dependencies: bookkeeping
Applicability: Every source whose processing or publication produces journal events and delivery receipts.

## Question

What is the shortest sufficient entrypoint for a reader to perform this phase correctly using existing supported commands?

## Scope and evidence

Keep the entrypoint focused on applicability, prerequisites, exact supported commands, expected outputs, next owner and stop conditions. Inputs: producer event identity, source and content fingerprints, processing identity and delivery destination. Outputs: durable event and receipt evidence plus a truthful delivery status. Open optional references only when needed; do not move a hard stop out of the required reading path.

Check existing splits before proposing another move; line count alone is not a completion measure.

Start from skills/change-journal/SKILL.md: Skipping and forcing, Required independence, Validate, Recover delivery. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Make the entrypoint executable](./03-data-platform-entrypoint.md); [bookkeeping: Make the entrypoint executable](./45-bookkeeping-entrypoint.md); [change-journal: Reconcile shared rules](./50-change-journal-consistent-rules.md)

Priority rationale: Producer completion and delivery evidence must remain distinct.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [ ] Produce an entrypoint that consumes producer event identity, source and content fingerprints, processing identity and delivery destination and yields durable event and receipt evidence plus a truthful delivery status.
- [ ] Verify referenced paths and supported commands; retain mandatory stops and discoverability of optional detail.
- [ ] Walk one applicable example to its handoff without loading unrelated references or repeating another skill's procedure.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
