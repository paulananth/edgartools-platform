# Reprovision Missing Phase 1 Bootstrap SQL on the Rebuilt Account

Type: task
Status: resolved
Blocked by: none

## Question

[Estimate Snowflake Compute Cost for Native Silver](08-estimate-snowflake-compute-cost.md)'s
research surfaced that the live Snowflake account (`PRJEDJU-QJB05385`,
`AWS_US_WEST_2`) was rebuilt from scratch on 2026-08-17/18 — after Phase 1's
Tickets 05 and 07 were built and verified live against a prior account
(`pijjxma-ppb32800` per Ticket 07's own text). On the rebuilt account:

- The 30 silver `dynamic_table` models (Ticket 01) **are** deployed
  correctly (confirmed via `GET_DDL`) — dbt's models were re-applied as
  part of whichever install-provisioning stage runs `dbt run` for gold/
  silver.
- **`LOAD_SILVER_LANDING_TASK`** — Ticket 07's scheduled `COPY INTO` task
  that dual-writes bronze-capture output into `EDGARTOOLS_SILVER_LANDING` —
  **does not exist on this account.** `infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql`
  was never (re-)applied here. Confirmed live: `SHOW TASKS IN DATABASE
  EDGARTOOLS_PROD` returns exactly one task
  (`SNOWFLAKE_RUN_MANIFEST_TASK`) — `LOAD_SILVER_LANDING_TASK` is absent
  entirely, not present-but-suspended.
- Consequence: `EDGARTOOLS_SILVER_LANDING` and `EDGARTOOLS_SILVER` are
  fully schema-provisioned but 100% empty (0 rows in all 61 tables/views),
  and have had zero scheduled dynamic-table refreshes in the account's
  entire history — every refresh so far was `CREATION`-triggered by the
  dbt deploy pass itself, not real ongoing operation.

This makes Ticket 08's cost estimate a bounding model rather than a
measurement, and means Tickets 09/10 (consumer cutover order, rollback
mechanics) would be deciding against a Snowflake-native silver layer that
has never actually received real data on this account — the "already live
in prod" status Phase 1's tickets recorded no longer describes the current
account.

**This ticket is the reprovisioning task itself, not a re-investigation.**
The bootstrap SQL, Terraform, and IAM changes Ticket 07 already designed
and committed exist unchanged in the repo — apply them to the current
account:

1. Apply `infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql`
   against `PRJEDJU-QJB05385` (creates the file format, stage, load
   procedure, and `LOAD_SILVER_LANDING_TASK`, owned by
   `EDGARTOOLS_PROD_LOADER` per Ticket 07's already-decided ownership
   policy — do not create as `ACCOUNTADMIN`).
2. Confirm the storage integration (`native_pull`'s
   `storage_allowed_locations`/`additional_storage_locations`) and the AWS
   IAM role's export-prefix allowlist (`runtime_access`'s
   `additional_export_prefixes`) both already include the silver-landing
   prefix on this rebuilt account — Ticket 07's Terraform source is
   committed, so this should already be correct if the account's
   Terraform roots were applied as part of the current install
   provisioning; verify rather than assume, the same way Ticket 07's own
   original pass caught a live IAM gap Terraform alone didn't surface.
3. Confirm `SILVER_LANDING_EXPORT_ROOT` is set in the current deployed
   warehouse task definition's environment (Ticket 07's PR #412 change) —
   if the account rebuild also reset the ECS deploy manifest, this may
   need re-flowing through `deploy-aws-application.sh` again.
4. **Separately, while in this account: fix the live
   `SNOWFLAKE_RUN_MANIFEST_TASK` 1-minute schedule drift** Ticket 08's
   research also surfaced (`schedule: 1 MINUTE` live, vs. the 6-hour value
   both Terraform and CLAUDE.md's documented incident say it should be).
   Not blocking for this ticket's own scope, but it's the same account,
   same investigation, and per CLAUDE.md's own "Dev Terraform/Snowflake
   go-live blockers" precedent this exact drift has recurred before —
   worth closing in the same pass rather than leaving it as a second,
   separately-discovered live cost bleed.
5. Once (1)-(3) are live, run a small real backfill (e.g. one
   `bootstrap-next` window) so `EDGARTOOLS_SILVER_LANDING` receives real
   rows, confirm `LOAD_SILVER_LANDING_TASK` picks them up, and confirm at
   least one silver dynamic table produces a real `refresh_trigger =
   'SCHEDULED'` row in `DYNAMIC_TABLE_REFRESH_HISTORY` — closing Ticket
   08's own "Recommended next steps."

## Answer

All five items done live against `PRJEDJU-QJB05385`, plus one additional
real bug found and fixed along the way that none of the original five
anticipated.

**(1) `13_silver_landing_ingest.sql` applied.** Confirmed live beforehand
that `EDGARTOOLS_PROD_LOADER` had neither `EXECUTE TASK ON ACCOUNT` nor the
schema-level `CREATE FILE FORMAT/STAGE/PROCEDURE/TASK` grants — exactly the
"never applied here" state Ticket 08 predicted. Ran the script via
`snowconn` (ACCOUNTADMIN, required for the one-time grants; the script
switches to `EDGARTOOLS_PROD_LOADER` internally for every CREATE, per
Ticket 07's ownership policy). `PARQUET_FORMAT`, `LANDING_STAGE`, the
`LOAD_SILVER_LANDING` procedure, and `LOAD_SILVER_LANDING_TASK` all created
successfully; task resumed.

**(2) Storage integration / IAM allowlist confirmed already correct** —
Ticket 07's committed Terraform did survive the rebuild here, unlike (1).
`DESC STORAGE INTEGRATION EDGARTOOLS_PROD_EXPORT_INTEGRATION` shows both
`snowflake_exports/` and `silver_landing/` in `STORAGE_ALLOWED_LOCATIONS`;
the live IAM policy (`edgartools-prod-snowflake-s3` role, policy name
`edgartools-prod-snowflake-export-s3-read` — not `snowflake_storage_reader`,
the Terraform *resource* label, which doesn't match the deployed policy
*name*; a naming trap worth remembering for the next person who greps for
it) shows the same `silver_landing/*` resource ARNs. No live-only patch
needed for this item, unlike (1).

**(3) `SILVER_LANDING_EXPORT_ROOT` confirmed already set** on the live
`edgartools-prod-medium` task definition, correct value. No action needed.

**(4) `SNOWFLAKE_RUN_MANIFEST_TASK` schedule drift fixed.** Confirmed live
at `1 MINUTE`/`started` before the fix. Same missing-`terraform apply`-
credential blocker Ticket 07 hit (`password is empty` against the
`snowflake` authenticator, no state-bucket-side workaround available this
session) ruled out fixing it via the committed Terraform module — used the
same direct-`ALTER TASK` pattern already established for exactly this
blocker class: `SUSPEND` → `SET SCHEDULE = '360 MINUTE'` → `RESUME`.
Verified live afterward: `schedule: 360 MINUTE`, `state: started`.

**(5) End-to-end verification — and a second, previously-unknown bug found
in the process.** Ran a real one-off `bootstrap-batch --cik-list 320193`
ECS task (Apple; `bootstrap-next` was tried first and rejected —
`--cik-list` doesn't exist on that command despite CLAUDE.md's Phased
Pipeline section saying it does; `bootstrap-batch` is the actual command
with that flag, confirmed from the exact command shape Stage 14's own
failing tasks used earlier in this session). The task succeeded and wrote
3 real rows to the silver-landing export
(`silver_landing_export_completed`, `sec_employment_event`). But
`LOAD_SILVER_LANDING_TASK`'s first real scheduled run (5 minutes later)
**failed**: `Execution error in store procedure LOAD_SILVER_LANDING: NULL
result in a non-nullable column`.

Root-caused (5-whys): `GET_DDL` on `sec_employment_event` showed
`PARSE_SEQUENCE NUMBER(38,0) NOT NULL` live, despite
`11_silver_landing_schema.sql`'s `CREATE TABLE` text never declaring
`parse_sequence NOT NULL` — the exact fix Ticket 07 already claimed to have
made. Cause: **Snowflake implicitly forces `NOT NULL` on any column named
in a `PRIMARY KEY` clause, regardless of the column's own declaration** —
a real Snowflake behavior neither Ticket 07 nor this repo's docs had
previously identified. Ticket 07's original fix only dropped the
*explicit* `NOT NULL` text; the actual nullability it achieved on the
*old* account came from a **separate, live-only** `ALTER TABLE ... DROP
NOT NULL` documented only in that ticket's Answer prose, never captured in
the committed generator. That live-only step did not survive this
account's rebuild — a second instance of the exact "provisioning step
without a re-runnable script" failure class this whole ticket exists to
close (see CLAUDE.md's "MDM Snowflake mirror schema lost on cutover").

**Fixed at the root, not patched live-only again**:
`infra/scripts/generate_silver_landing_ddl.py` now emits an explicit
`ALTER TABLE <table> ALTER COLUMN parse_sequence DROP NOT NULL;`
immediately after every `CREATE TABLE IF NOT EXISTS <table> (...)` block —
idempotent (re-running `DROP NOT NULL` against an already-nullable column
is a no-op, confirmed by this same live application). Regenerated
`infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql` (diff
confirmed to be exactly the 31 new `ALTER TABLE` lines, header/grants/
column lists byte-identical otherwise) and applied it live — `CREATE TABLE
IF NOT EXISTS` no-op'd on all 31 already-existing tables, all 31 `ALTER`
statements executed and made `parse_sequence` genuinely nullable this
time. New regression test,
`tests/unit/test_generate_silver_landing_ddl.py` (3 tests: every table
gets the ALTER, the ALTER directly follows its own table's CREATE not just
anywhere in the file, and the statement is the plain non-guarded form) —
confirmed to fail 3/3 against the pre-fix generator via `git stash`, passes
after.

**Full chain re-verified live after the fix**: manually invoked `CALL
LOAD_SILVER_LANDING()` as `EDGARTOOLS_PROD_LOADER` — succeeded, loaded
4,055 rows across 6 tables (`sec_employment_event`: 1,506,
`sec_filing_attachment`: 2,360, `sec_raw_object`: 108,
`sec_ownership_reporting_owner`: 44, `sec_ownership_non_derivative_txn`:
36, `sec_ownership_derivative_txn`: 1) — far more than the one verification
task wrote, confirming this also drained a real backlog of files that
Stage 14's earlier (171+101-batch) runs had already exported to S3 but had
nowhere to land until `LOAD_SILVER_LANDING_TASK` existed. Manually
refreshed one dynamic table (`ALTER DYNAMIC TABLE
EDGARTOOLS_SILVER.SEC_EMPLOYMENT_EVENT REFRESH`) to prove the model logic
itself works against real data (not just empty-table `CREATION` triggers):
succeeded, `insertedRows: 1506`; `SELECT COUNT(*)` on the dynamic table
confirms 1,506.

**Not fully closed**: a genuine `refresh_trigger = 'SCHEDULED'` row (vs.
this session's manual `REFRESH`) still requires either a real downstream
consumer on a `DOWNSTREAM`-lag table or a fixed `TARGET_LAG` — neither
exists yet, confirmed structural (§4b of Ticket 08's research: 0 of 87
lifetime refreshes in this account have ever been `SCHEDULED`-triggered).
That's [Decide Consumer Cutover Order](09-decide-consumer-cutover-order.md)
and [Decide Cutover/Rollback Mechanics](10-decide-cutover-rollback-mechanics.md)'s
job, not this ticket's — the pipeline is now provably capable of feeding
real data through to a correct dynamic-table result; whether it does so on
a schedule is the next map phase's decision.

