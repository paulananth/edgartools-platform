# data-governance: Make progress resumable

Type: task
Status: open
Blocked by: 63, 04
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-governance](../../../skills/data-governance/SKILL.md)
Step: 4 of 6
Applicability: Every source's governed outputs and lineage claims.

## Question

What evidence allows another session to resume this phase without repeating completed work or trusting stale results?

## Scope and evidence

Use the existing onboarding log or task record as the common progress record, not a new independent state store per skill. Record governed graph version, source and output inventory, evidence references and missing or unverified edges. Define when unchanged evidence is reused, invalidated or blocked; retain unfinished work explicitly.

A handoff must identify the next owning skill: data-catalog for business presentation and a destination-specific skill for publication.

Start from skills/data-governance/SKILL.md: What is governed, Completion; LINEAGE.md. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-governance: Make the entrypoint executable](./63-data-governance-entrypoint.md); [data-platform: Make progress resumable](./04-data-platform-resume.md)

## Acceptance checklist

- [ ] Specify resume, invalidate and blocked conditions for governed graph version, source and output inventory, evidence references and missing or unverified edges.
- [ ] Resume a staged interruption from the recorded artifacts and identify exactly the first unfinished action.
- [ ] Show changed inputs cannot reuse stale proof and unchanged inputs do not repeat completed work.
- [ ] Publish the scoped change and evidence in its own branch and PR; run the affected checks required by CLAUDE.md.
- [ ] Learning → skill: name the verified reusable lesson and its owning skill section, or record none.

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.
