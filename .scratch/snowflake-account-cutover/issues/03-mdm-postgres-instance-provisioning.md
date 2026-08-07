# Find and document what actually provisions the Snowflake-hosted MDM Postgres instance

Type: task
Status: resolved

## Question

`infra/scripts/bootstrap-prod-mdm.sh` requires the target Snowflake Postgres
instance (e.g. `EDGARTOOLS_PROD_MDM`) already be in `READY` state — line 113,
`DESCRIBE POSTGRES INSTANCE ${INSTANCE_NAME}` must succeed and report READY
before the script does anything else. It does not create the instance
itself.

Find whatever actually provisions a Snowflake Postgres instance (Terraform
resource? A separate one-off `CREATE POSTGRES INSTANCE` SQL command run
manually when prod was first set up? Something in one of the Terraform
modules already surveyed in the snowflake-env-provisioning map?) and
document: (a) is it reusable/scriptable for a second account, or was it a
manual one-time step for the original prod account that was never
captured in code; (b) if manual, what exactly needs to be run against
`pijjxma-ppb32800` to get an instance into READY state before
`bootstrap-prod-mdm.sh` can be called.

## Notes

`task`-type (AFK) — this is finding and documenting an existing mechanism
(or its absence), not deciding between alternatives. If the answer turns out
to be "nothing provisions this yet, it's undocumented tribal knowledge,"
that's still a valid, useful answer — it just means the go-live runbook
(Ticket 06) needs to spell out the manual step explicitly rather than
delegate to a script.

## Answer

**(a) It IS reusable/scriptable — the SQL already exists, parameterized
correctly — but it is genuinely not wired into any repeatable script
today, and `go-live.sh` itself has dead scaffolding suggesting an
abandoned attempt to wire it in.**

Two real, parameterized SQL files already exist and require no new code:

- `infra/snowflake/postgres/mdm_create_network_policy.sql` — creates a
  `NETWORK RULE` + `NETWORK POLICY` (Jinja `-D` vars: `schema`,
  `network_rule_name`, `network_policy_name`). Must run first — Snowflake
  Postgres instances reject a `NETWORK_POLICY` that lacks a
  `POSTGRES_INGRESS`-mode rule.
- `infra/snowflake/postgres/mdm_create_instance.sql` — `CREATE POSTGRES
  INSTANCE {{ instance_name }} ... NETWORK_POLICY = '{{ network_policy }}'`
  (Jinja vars: `instance_name`, `network_policy`, `comment_env`).

Both are documented as manual `snow sql --filename ...` invocations in
`docs/aws-mdm-snowflake-postgres-cutover.md` (Step 1, "Provision Snowflake
Postgres") — but that whole doc is the **historical AWS-RDS-to-Snowflake
migration runbook** from the original cutover; only its Step 1 is relevant
here. Steps 2-6 (pg_dump/pg_restore from RDS, secret rewrite, RDS removal)
assume an existing RDS source to migrate *from* — not applicable to a
brand-new account, which has no RDS at all; MDM data there gets
*regenerated* via `mdm run`, not restored (consistent with this map's own
Destination).

**Confirmed not wired into `go-live.sh`, and not by omission —
`go-live.sh` computes the exact right parameter values and then never uses
most of them.** `write_snowflake_stage_plan()`
(`go-live.sh:635-642`) computes `mdm_instance_name`, `mdm_network_policy_name`,
`mdm_network_rule_name`, and `mdm_schema_name` — correct values, matching
what the two SQL files above need. But grep across the whole file shows
only `mdm_instance_name_q` is ever actually used (passed to
`bootstrap-prod-mdm.sh --instance-name` at line 718, which per this
ticket's own premise just checks the instance is already `READY`).
`mdm_network_policy_name_q`, `mdm_network_rule_name_q`, and
`mdm_schema_name_q` are computed and never referenced again anywhere in
the file — dead variables, reading like an abandoned attempt to add a
stage that runs these two SQL files, never finished.

**A third, deeper prerequisite gap, not mentioned by either SQL file's own
header comments:** `mdm_create_network_policy.sql`'s `USE SCHEMA
{{ schema }}` (e.g. `EDGARTOOLS_PROD.MDM`) requires that Snowflake schema
to already exist. Confirmed via `infra/terraform/snowflake/modules/account_baseline/main.tf:2-5`
that Terraform's baseline module only creates `source` and `gold` schemas
— no `MDM` schema anywhere in Terraform. Confirmed via grep that nothing
else creates it either (`edgar_warehouse/mdm/export.py`'s
`SnowflakeConnectorWriter`, which later reads/writes against
`schema="MDM"` per `mdm/cli.py:1862`, has no `CREATE SCHEMA` of its own —
it assumes the schema exists). On the current prod account this schema
must have been created manually at some point (CLAUDE.md's Snowflake-DEV
decommission note independently confirms `MDM` existed as one of dev's 8
schemas, created the same ad hoc way). **A brand-new account has no `MDM`
schema at all — running `mdm_create_network_policy.sql` as-is against
`pijjxma-ppb32800` would fail at `USE SCHEMA` before creating anything.**

**(b) What must run against `pijjxma-ppb32800`, in order, before
`bootstrap-prod-mdm.sh` can be called:**

1. `CREATE SCHEMA IF NOT EXISTS EDGARTOOLS_PROD.MDM;` (not currently
   scripted anywhere — the newly-found gap above).
2. `snow sql --connection edgartools-prod --filename infra/snowflake/postgres/mdm_create_network_policy.sql -D "schema=EDGARTOOLS_PROD.MDM" -D "network_rule_name=mdm_postgres_ingress_all" -D "network_policy_name=edgartools_prod_mdm_postgres_policy"`
3. `snow sql --connection edgartools-prod --filename infra/snowflake/postgres/mdm_create_instance.sql -D "instance_name=EDGARTOOLS_PROD_MDM" -D "network_policy=edgartools_prod_mdm_postgres_policy" -D "comment_env=prod"` — capture the generated `snowflake_admin`/`application` credentials immediately; Snowflake never shows them again.
4. Only then does `bootstrap-prod-mdm.sh`'s `DESCRIBE POSTGRES INSTANCE`
   precondition (line 113) succeed.

**Not resolved here, by design** (per this ticket's own Notes): whether
steps 1-3 become a new `go-live.sh` stage (which could finish wiring the
already-computed-but-unused `mdm_schema_name_q`/`mdm_network_policy_name_q`/
`mdm_network_rule_name_q` variables) or stay a documented manual runbook
step. That placement decision belongs to Ticket 06 (assembling the go-live
runbook), which already covers exactly this kind of staging choice — not
spun out as its own ticket.
