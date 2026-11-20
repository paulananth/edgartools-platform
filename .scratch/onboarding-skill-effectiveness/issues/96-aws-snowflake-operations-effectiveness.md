# aws-snowflake-operations: Measure effectiveness

Type: task
Status: open
Blocked by: 95, 06
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [aws-snowflake-operations](../../../skills/aws-snowflake-operations/SKILL.md)
Step: 6 of 6
Applicability: Conditional: onboarding touches AWS, Snowflake, hosted connections, images or deployment.

## Question

Does the revised skill improve observed task outcomes compared with a recorded baseline?

## Scope and evidence

Record baseline and revised behavior on comparable representative tasks: an absent hosted prerequisite, a stale deployed image and a deployment blocked before local qualification. Measure manual provisioning, stale-runtime false positives, unauthorized target selection and time spent on avoidable deployment. Record task inputs, skill revisions, active versus waiting time, command outcomes and limitations; do not claim improvement from shorter text alone.

Carry unchanged evidence forward. Choose acceptance targets before the comparison and retain any regression or unavailable live proof explicitly.

Start from skills/aws-snowflake-operations/SKILL.md: Data layers, The hosted MDM store, Pipeline and runtime rules, Image management. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[aws-snowflake-operations: Specify generic verification](./95-aws-snowflake-operations-generic-verification.md); [data-platform: Measure effectiveness](./06-data-platform-effectiveness.md)

## Acceptance checklist

- [ ] Record a reproducible baseline and predeclared improvement targets for manual provisioning, stale-runtime false positives, unauthorized target selection and time spent on avoidable deployment.
- [ ] Compare the revised skill on matching scenarios; attribute waiting time and unavailable evidence explicitly.
- [ ] Report measured gains and regressions, remaining limitations and whether the targets were met.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

