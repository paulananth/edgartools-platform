# data-modeling: Distinguish Silver source keys from resolved master IDs

Type: task
Status: claimed
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

- [x] Clarify source-key links in [Data Modeling: A transaction part](../../../skills/data-modeling/SKILL.md#6-a-transaction-part-its-silver-table); class guidance points there and keeps master attributes in MDM. No other link modes or source rules changed. (2026-11-25 07:00 ET)
- [x] Verify the configured fact and read-time join with `test_the_custody_fact_links_to_the_master_without_copying_its_name`: **1 passed** on disposable PostgreSQL 16. Genericity, guide path and skill lint: **163 passed**. No new scenario added. (2026-11-25 07:00 ET)
- [ ] Publish the skill correction and evidence on its own branch and PR.
- [x] Learning → skill: [A transaction part: its silver table](../../../skills/data-modeling/SKILL.md#6-a-transaction-part-its-silver-table) distinguishes stored source keys from master IDs resolved at read time. (2026-11-25 07:00 ET)

## Answer

For a source-key link, the Silver fact stores its own facts and the declared source key. The reader joins `silver.master_binding` on the Dataset Contract source code and key to resolve the master ID; that ID is not a stored fact column. Master attributes stay in MDM. The existing custody integration test read the amount at its fact grain, resolved the master ID by the binding join, and found the name only in MDM. This verifies the storage contract, not a change in agent behavior. No runtime or source configuration changed.
