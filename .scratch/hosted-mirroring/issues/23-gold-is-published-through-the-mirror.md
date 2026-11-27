# 23: Gold is published through the mirror, and the mirror is made again after the load

Status: open
Type: task
Owner: claude (operator, 2026-11-26: "review the repo the gold is published usin mirror, restablish cleanup md files context memory")

An agent answered that nothing writes Snowflake Gold because CLAUDE.md said "the platform ends at silver; gold and dashboards
come later", and the Snowflake skill said the stores sat in separate databases that one mirror could not combine. Both are
wrong: one managed mirror of the data database carries the tables `sources/managed-mirror.yaml` lists, and Gold is dbt views
over it. Gold is empty now because the mirror is absent: the store clear of 2026-11-26 11:16 ET found `LIST_MIRRORS` naming no
mirror and the target database absent, and `managed-mirror.yaml` reads `verified: false`.

## Checklist

- [x] CLAUDE.md states that Gold is published in Snowflake through the one managed mirror, with the operator's words, and points to HOSTED-MIRRORING (read in the diff) (2026-11-26 20:16 ET)
- [x] `aws-snowflake-operations/SKILL.md`, "Data layers": the mirror carries the listed tables of the one data database, Gold is dbt views over it, a reset removes the mirror and it is made again after the next load, a dropped target's name is not reused (read in the diff) (2026-11-26 20:16 ET)
- [x] `data-modeling/GOLD.md`: Gold's destination is `gold` in `rules/snowflake.yaml`, written from `destination/gold/gold.yaml`, not "undecided" (read in the diff) (2026-11-26 20:16 ET)
- [x] CONTEXT.md: Managed Mirror and Gold defined; Canonical Silver is the data database's `silver` schema; the Loader Role (owner of deleted dynamic tables and procedures, absent from code and infra by `git grep`) removed (2026-11-26 20:16 ET)
- [x] `data-operations/SKILL.md`: a hosted load writes MDM, RDM and Silver to the data database on Snowflake Postgres, and Snowflake reads them only through the mirror; no silver is built in Snowflake (operator, 2026-11-26: "we are not building silver in snowflake only mirror mdm, rdm, and silver"; `git grep` finds no other `EDGARTOOLS_SILVER` or Snowflake-sink text in skills, docs or CLAUDE.md) (2026-11-26 20:16 ET)
- [x] Memory: the note "there is no production Snowflake now" deleted with its index line (2026-11-26 20:16 ET)
- [ ] Make the mirror again after the load `hosted-lanes-20261126` and its finish: a new `mirror.database` in `rules/snowflake.yaml` (the target `EDGARTOOLS_MIRROR` was made and dropped), exposure `generate` and `check`, the pre-flight, `mirror_sql.py plan` presented with every table's size (approved when presented once the load has finished, operator 2026-11-19 14:41 ET, gold-warehouse ticket 06), `create`, `verify`, `readback`, then `verified: true`
- [ ] Grant the Gold writer read on the new mirror database, write the Gold project (`python -m edgar_warehouse.gold.views write infra/dbt/gold`), run it, and read back that each Gold view returns rows
- [x] Operator, 2026-11-26, on how far the cleanup of the old architecture goes: "Docs now, infra next (Recommended)": every doc, skill and CONTEXT.md line now; then an inventory of what of the old Terraform is live in AWS, brought back as one removal plan with `terraform plan` output before anything is applied (2026-11-26 20:23 ET)
- [x] CONTEXT.md: the old pipeline's glossary removed: the Step Functions machine families (their builders are absent from the code), the MDM Run Identity and Commit Evidence of those machines, and the release-readiness, MdmExport and hosted-graph terms; `git grep` finds none of them in code, skills, ADRs or runbooks. Reported Executive Employment kept, beside the other data terms; MDM Commit Evidence and Current-at-Watermark Relationship, which current terms use, kept with definitions that name a Bookkeeping run and an as-of date (review finding) (2026-11-26 20:23 ET)
- [x] `docs/agents/aws.md`, "Runtime Settings": the warehouse variables (`WAREHOUSE_*`, `SERVING_EXPORT_ROOT`, S3 export roots) removed, since no code reads them; the identity and connection notes kept (2026-11-26 20:23 ET)
- [ ] Old infrastructure, the operator's "infra next": inventory what is live in AWS of the Snowflake export bucket and its KMS key, the S3 bronze buckets, the warehouse runtime module and the EventBridge schedule of `edgartools-prod-mdm-utility`; keep `daily_incremental` and what it needs (operator, 2026-11-26: "daily_incremental will be rewritten keep that only"); bring one removal plan with `terraform plan` output; then remove the Terraform, `infra/scripts/*bronze*`, `preflight-prod-promotion.sh` and its test, `tests/architecture/test_cloudwatch_log_retention.py` (it cites the release-readiness term Operational Forensics Window), and the AWS guide's bucket table with them
- [ ] The legacy specs under `docs/specs/mdm` and `docs/specs/mdm-enrichment`, which call themselves the historical legacy-stack contract (`recovery.md`, `acceptance.md`'s Snowflake export and hosted graph): keep what the rebuild still uses, remove the rest
- [x] Learning → skill: `aws-snowflake-operations/SKILL.md`, "Data layers" (Gold is published through the mirror; the mirror is absent between a reset and the next load's finish) (2026-11-26 20:16 ET)
