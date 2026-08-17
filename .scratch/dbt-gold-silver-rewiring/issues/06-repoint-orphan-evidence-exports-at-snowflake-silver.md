# 06 — Repoint the Orphan Evidence-Table Exports at Snowflake Silver Directly

**What to build:** Five `gold_models.py` Python builders have no dbt gold
model at all today — `sec_subsidiary_evidence`, `sec_auditor_report_evidence`,
`sec_employment_event`, `sec_adv_firm_roster`, and `sec_adv_private_fund`
(the passthrough export, distinct from the dimensional `private_funds` table
in Ticket 04) — they write straight into `EDGARTOOLS_SOURCE` with nothing
downstream consuming them via dbt `ref()`. Since there's no dbt cutover path
for tables nothing `ref()`s, this ticket repoints each export's read from
local DuckDB to Snowflake silver directly, independent of the dbt-facing
batches in Tickets 02-05.

**Blocked by:** None — can start immediately, independent of Tickets 02-05

**Status:** ready-for-agent

- [ ] All 5 exports read from Snowflake silver instead of local DuckDB
- [ ] Output row content matches today's DuckDB-backed export per the
      cutover validation standard
- [ ] No behavior change for any downstream consumer of these 5
      `EDGARTOOLS_SOURCE` tables
