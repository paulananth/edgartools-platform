# data-onboarding: Measure effectiveness

Type: task
Status: open
Blocked by: 23, 06
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-onboarding](../../../skills/data-onboarding/SKILL.md)
Step: 6 of 6
Applicability: Every new source or new kind; live-source revisions route to refining-rules.

## Question

Does the revised skill improve observed task outcomes compared with a recorded baseline?

## Scope and evidence

Record baseline and revised behavior on comparable representative tasks: a multi-part source with master, reference and transaction parts, then an interrupted configuration build. Measure time from findings to a verified configuration, repeated profiling, source-specific code introduced and missing handoff artifacts. Record task inputs, skill revisions, active versus waiting time, command outcomes and limitations; do not claim improvement from shorter text alone.

Carry unchanged evidence forward. Choose acceptance targets before the comparison and retain any regression or unavailable live proof explicitly.

Start from skills/data-onboarding/SKILL.md: Modes in order, The files are the rules, metadata, check and load; MAP.md and TARGETS.md. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

The prior split is recorded in [The data-onboarding skill is split behind pointers](../../rebuild-priorities/issues/215-split-the-data-onboarding-skill.md); inspect current references before repeating it.

## Prerequisites

[data-onboarding: Specify generic verification](./23-data-onboarding-generic-verification.md); [data-platform: Measure effectiveness](./06-data-platform-effectiveness.md)

## Acceptance checklist

- [ ] Record a reproducible baseline and predeclared improvement targets for time from findings to a verified configuration, repeated profiling, source-specific code introduced and missing handoff artifacts.
- [ ] Compare the revised skill on matching scenarios; attribute waiting time and unavailable evidence explicitly.
- [ ] Report measured gains and regressions, remaining limitations and whether the targets were met.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

