# 227: The `aws-snowflake-operations` skill holds rules, not history

Priority: 227, housekeeping. Map: [Rebuild priorities](../map.md). Opened 2026-11-11 19:52 ET (operator: "remove the dates and run figures from the skills too also make skills focused on the task or the function it is created for"). Part of [214](214-skills-organized-one-index-one-link-script.md).

Type: task. Status: open.

## Checklist

- [x] (2026-11-11 19:52 ET) 8 dates removed. Verified by the date script: none left
- [x] (2026-11-11 19:52 ET) The two teardown stories are cut to their rules: the old AWS account is decommissioned, empty and never reprovisioned, and closing it is a root action; there is no dev environment on AWS or Snowflake, and anything that names one is stale. The counts of what was destroyed go
- [x] (2026-11-11 19:52 ET) "Known open items" leaves the skill: it is a backlog, not a rule. Its three items are kept below, word for word
- [x] (2026-11-11 19:52 ET) "ECS cost sizing (old pipeline)" becomes "Sizing a worker runtime": the method stays, the old pipeline's story goes
- [x] (2026-11-11 19:52 ET) Ticket-citation and genericity lints pass; the doctor's skill check returns nothing
- [ ] The three open items below: each needs an owner or a decision to drop it
- [x] (2026-11-11 19:52 ET) Learning → skill: none here; the rule and its lint land with ticket 214's closing PR

## Open items moved out of the skill

Deploy status is as last recorded; re-check against the running image before trusting it.



- **The `EDGARTOOLS_DECISION` schema does not exist**, leaving 5 Terraform-managed grants unapplied.
  `infra/snowflake/sql/decision_contract/01_subject_feature_screen.sql`'s "MDM active-company universe"
  join is an explicit placeholder that self-joins `COMPANY`, and
  `infra/snowflake/sql/decision_contract/02_subject_bundle_read_issuer.sql`'s `BUNDLE_AUDITOR` references
  `EDGARTOOLS_GOLD.SEC_AUDITOR_REPORT_EVIDENCE`, which exists only in `EDGARTOOLS_SOURCE`. The real
  blocker behind both: no Snowflake-side source has been chosen for "MDM active company universe" (MDM's
  authority is Postgres; the closest reflection is `NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES`).
- **The original `EDGARTOOLS_DASHBOARD` Streamlit app is still ACCOUNTADMIN-owned** — the same gap already
  fixed for `MDM_GRAPH_DASHBOARD`, with the same drop/recreate-as-target-role recipe.
- **Stale bronze objects:** repairing the two known stale accessions, and a proactive
  scan for other pre-2026-07-31 stale bronze objects.

