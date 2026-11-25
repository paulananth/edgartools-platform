# data-modeling: Distinguish Silver source keys from resolved master IDs

Type: task
Status: open
Priority: P0
Blocked by: 18
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-modeling](../../../skills/data-modeling/SKILL.md)

## Question

How should the Data Modeling handoff describe a source-key link so the fact's stored columns are not confused with the master ID that a reader joins in?

## Evidence

[Measure effectiveness](./18-data-modeling-effectiveness.md#answer) found both skill revisions proposed storing a master ID on the custody fact. [Data Modeling's class guidance](../../../skills/data-modeling/SKILL.md#1-class) calls out the source key and then the master ID without distinguishing storage from lookup. The [stored fact proof](./17-data-modeling-generic-verification.md#answer) obtains the master ID by a join on `master_binding`; the [custody spec](../../../sources/iapd.adv/silver-custody.yaml) stores the fact and its source key. The issue is a handoff ambiguity, not a missing writer feature.

## Acceptance checklist

- [ ] Clarify the generic source-key link path in the owning skill: the fact stores its source key, the reader resolves the master ID through `master_binding`, and master attributes stay in MDM. Do not change unrelated link modes or source rules.
- [ ] Verify the wording against the configured writer/readback evidence and run the affected documentation checks. No new test scenario without approval.
- [ ] Publish the skill correction and evidence on its own branch and PR.
- [ ] Learning → skill: name the clarified handoff section.
