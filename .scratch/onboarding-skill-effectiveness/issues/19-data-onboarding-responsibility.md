# data-onboarding: Define one responsibility

Type: task
Status: open
Blocked by: 01
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-onboarding](../../../skills/data-onboarding/SKILL.md)
Step: 1 of 6
Applicability: Every new source or new kind; live-source revisions route to refining-rules.

## Question

Which decisions and artifacts belong here, and which must be handed to another skill?

## Scope and evidence

Establish this boundary: Turn the modeled parts into configured readers, Dataset Contracts, quality mappings, target declarations and steward artifacts.

Inventory existing instructions against the neighboring owners: bookkeeping for execution and data-operations for the local proof and operational handoff. Reconcile the current index and references before moving any text.

Start from skills/data-onboarding/SKILL.md: Modes in order, The files are the rules, metadata, check and load; MAP.md and TARGETS.md. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

The prior split is recorded in [The data-onboarding skill is split behind pointers](../../rebuild-priorities/issues/215-split-the-data-onboarding-skill.md); inspect current references before repeating it.

## Prerequisites

[data-platform: Define one responsibility](./01-data-platform-responsibility.md)

## Acceptance checklist

- [ ] List decisions, inputs and outputs owned here using current repository evidence.
- [ ] Assign each overlapping responsibility one authoritative owner and a named handoff.
- [ ] Demonstrate the boundary on a multi-part source with master, reference and transaction parts, then an interrupted configuration build; link retained work rather than duplicating it.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

