# Research findings: Ticket 03 — invocation plumbing and SNOWFLAKE_RUN_MANIFEST_TASK's fate

Status: research complete, findings only. Does NOT resolve the ticket (no
Status/Answer edit to issue 03, map.md untouched) — a separate step reviews
this and closes the ticket.

This is written from `.claude/worktrees/agent-a7abb9293f0bff067` (the ticket
file itself lives only in the main checkout at
`/Users/aneenaananth/projects/edgartools-platform/.scratch/snowflake-daily-load-trigger/issues/03-decide-invocation-plumbing-and-task-object-fate.md`
— it hasn't been merged into this worktree's branch yet, but the repo files
this research depends on (`infra/snowflake/sql/bootstrap/*`,
`infra/terraform/snowflake/modules/native_pull/main.tf`) exist identically
in both).

---

## Sub-question 1 — Credential/role fit for `PROCESS_RUN_MANIFEST_STREAM`

### Where the procedure actually lives (correction to the ticket's file pointer)

The ticket and CLAUDE.md's own "Manifest-pipeline ownership" 5-whys point at
`infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql` as "the file
that defines `PROCESS_RUN_MANIFEST_STREAM`." **That's stale** — file number
`13` was reused later (silver-snowflake-migration workstream, Ticket 07) for
an unrelated apparatus (`LOAD_SILVER_LANDING` / `LOAD_SILVER_LANDING_TASK`,
a plain scheduled `COPY INTO` loader for a completely different schema,
`EDGARTOOLS_SILVER_LANDING`). `PROCESS_RUN_MANIFEST_STREAM` is actually
defined in **`infra/snowflake/sql/bootstrap/04_refresh_wrapper.sql:197-242`**,
alongside `REFRESH_AFTER_LOAD` (same file, lines 19-195). The third procedure
in the chain, `LOAD_EXPORTS_FOR_RUN`, is in
**`infra/snowflake/sql/bootstrap/03_source_load_wrapper.sql:13-352`**.
Confirmed via `grep -rn "PROCESS_RUN_MANIFEST_STREAM"` across the whole repo
— only `04_refresh_wrapper.sql`, `03_source_load_wrapper.sql`, and
`08_loader_role.sql` reference it; `13_silver_landing_ingest.sql` does not.

### The full call chain and its EXECUTE AS clauses

`PROCESS_RUN_MANIFEST_STREAM()` calls both of the other two procedures
internally. All three are declared `EXECUTE AS OWNER` (Snowflake's default
if unspecified is actually `EXECUTE AS OWNER` too, but all three declare it
explicitly here):

| Procedure | File:line | Language | EXECUTE AS |
|---|---|---|---|
| `PROCESS_RUN_MANIFEST_STREAM()` | `04_refresh_wrapper.sql:197-200` | SQL (scripting) | `EXECUTE AS OWNER` |
| `LOAD_EXPORTS_FOR_RUN(workflow_name, run_id)` | `03_source_load_wrapper.sql:13-16` | JAVASCRIPT | `EXECUTE AS OWNER` |
| `REFRESH_AFTER_LOAD(workflow_name, run_id)` | `04_refresh_wrapper.sql:19-22` | JAVASCRIPT | `EXECUTE AS OWNER` |

`PROCESS_RUN_MANIFEST_STREAM`'s body (`04_refresh_wrapper.sql:216-241`)
calls the other two by their fully-qualified names:
```
CALL EDGARTOOLS_SOURCE.LOAD_EXPORTS_FOR_RUN(:r_workflow_name, :r_run_id);
CALL EDGARTOOLS_GOLD.REFRESH_AFTER_LOAD(:r_workflow_name, :r_run_id);
```

**`EXECUTE AS OWNER` means each procedure's body runs with its *owner
role's* privileges, regardless of which role issued the original `CALL`.**
This is standard Snowflake stored-procedure semantics (owner's-rights, the
default and the only mode for these three — none uses `EXECUTE AS CALLER`).
Since all three procedures share the same owner (see next section), the
identity of whoever triggers the outermost `CALL` only has to satisfy two
things: (a) be able to resolve/invoke that one outermost procedure, and
(b) have a warehouse to run on. Everything the procedure bodies themselves
touch (tables, the manifest stream, the gold dynamic tables) runs under the
owner's grants, not the caller's.

### Who owns all three procedures today

`infra/snowflake/sql/bootstrap/08_loader_role.sql:180-191` re-parents
ownership of all three onto `EDGARTOOLS_PROD_LOADER`:
```sql
USE SCHEMA IDENTIFIER($source_schema_name);
GRANT OWNERSHIP ON PROCEDURE IDENTIFIER($source_load_procedure_name)(VARCHAR, VARCHAR)
  TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;

USE SCHEMA IDENTIFIER($gold_schema_name);
GRANT OWNERSHIP ON PROCEDURE IDENTIFIER($refresh_procedure_name)(VARCHAR, VARCHAR)
  TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
GRANT OWNERSHIP ON PROCEDURE IDENTIFIER($stream_processor_procedure_name)()
  TO ROLE IDENTIFIER($loader_role_name) COPY CURRENT GRANTS;
```
where `$loader_role_name` = `EDGARTOOLS_PROD_LOADER` in prod and
`$stream_processor_procedure_name` = `PROCESS_RUN_MANIFEST_STREAM` (session
variables documented at the top of the same file, lines 39/44). This grant
transfer, and the incident that motivated it, is independently corroborated
by CLAUDE.md's "Manifest-pipeline ownership + cursor-syntax incident"
5-whys section — already-live, already-verified prod state, not a proposal.

### What a caller needs to run `CALL PROCESS_RUN_MANIFEST_STREAM()` directly, and whether `EDGARTOOLS_PROD_LOADER` already has it

Three things, all already granted to `EDGARTOOLS_PROD_LOADER`:

1. **USAGE on the database/schema to resolve the call.**
   `08_loader_role.sql:70,72`:
   `GRANT USAGE ON DATABASE IDENTIFIER($database_name) TO ROLE ...` and
   `GRANT USAGE ON SCHEMA IDENTIFIER($gold_schema_qualified) TO ROLE ...`
   (`$gold_schema_qualified` = `EDGARTOOLS_PROD.EDGARTOOLS_GOLD`, where the
   procedure lives).

2. **Privilege to invoke the procedure object itself.** In Snowflake, the
   OWNERSHIP privilege on an object inherently includes every other
   privilege on that object, including the implicit USAGE/CALL right — an
   owner never needs a separate grant to call its own procedure. Since
   `EDGARTOOLS_PROD_LOADER` *is* the owner (previous section), this is
   automatically satisfied; there is no separate "GRANT USAGE ON PROCEDURE"
   statement anywhere in the bootstrap SQL for this role, and none is
   needed.

3. **A warehouse to execute the procedure body's internal SQL statements
   on.** SQL-scripting and JavaScript stored procedures have no dedicated
   compute of their own — their internal statements run on whatever
   warehouse is active in the calling session. `08_loader_role.sql:73`:
   `GRANT USAGE ON WAREHOUSE IDENTIFIER($refresh_warehouse_name) TO ROLE
   IDENTIFIER($loader_role_name);` (`$refresh_warehouse_name` =
   `EDGARTOOLS_PROD_REFRESH_WH` — the same warehouse the manifest task
   itself already runs on, per `main.tf:724`).

### The existing secret already carries this role and a warehouse

`edgar_warehouse/mdm/export.py:64-96` (`SnowflakeConnectionSettings.from_env`)
reads `ACCOUNT`/`USER`/`PASSWORD`/`DATABASE`/`SCHEMA`/`WAREHOUSE`/`ROLE` out
of the `MDM_SNOWFLAKE_SECRET_JSON` env var (falling back to
`DBT_SNOWFLAKE_SECRET_JSON`) and passes all of them, including `role`, into
`snowflake.connector.connect(**kwargs)` (`connection_kwargs()`, lines 98-109
— `role` is included whenever non-empty). `SCHEMA` defaults to
`EDGARTOOLS_GOLD` if absent (line 71) — exactly the schema
`PROCESS_RUN_MANIFEST_STREAM` lives in, so an unqualified `CALL
PROCESS_RUN_MANIFEST_STREAM()` would resolve correctly even without
schema-qualifying the call.

`infra/scripts/bootstrap-prod-mdm.sh:311-333` shows how that secret's fields
are populated: it copies `DBT_SNOWFLAKE_ROLE`/`WAREHOUSE`/`ACCOUNT`/etc.
straight out of the `${NAME_PREFIX}/dbt/snowflake` secret into
`${NAME_PREFIX}/mdm/snowflake` (a one-time snapshot copy at bootstrap time,
not a live link) — a *different* script from
`deploy-snowflake-stack.sh` (next paragraph), which populates a different
secret for a different purpose and is not in this call path at all.

**Verified live** (field-only extraction — no password/account fields
printed, per this repo's own credential-handling convention):
```
$ aws secretsmanager get-secret-value --secret-id "edgartools-prod/mdm/snowflake" \
    --region us-east-1 --query SecretString --output text \
    | jq -r '.MDM_SNOWFLAKE_ROLE'
EDGARTOOLS_PROD_LOADER

$ aws secretsmanager get-secret-value --secret-id "edgartools-prod/mdm/snowflake" \
    --region us-east-1 --query SecretString --output text \
    | jq -r '{WAREHOUSE: .MDM_SNOWFLAKE_WAREHOUSE, SCHEMA: .MDM_SNOWFLAKE_SCHEMA, DATABASE: .MDM_SNOWFLAKE_DATABASE}'
{
  "WAREHOUSE": "EDGARTOOLS_PROD_REFRESH_WH",
  "SCHEMA": "EDGARTOOLS_GOLD",
  "DATABASE": "EDGARTOOLS_PROD"
}
```
This is the actual live `edgartools-prod/mdm/snowflake` secret in AWS
account `690839588395` as of this research pass — not an inference from
CLAUDE.md's incident history (which independently agrees, but is no longer
the only evidence). `ROLE` = `EDGARTOOLS_PROD_LOADER` (the owner of all
three procedures), `WAREHOUSE` = `EDGARTOOLS_PROD_REFRESH_WH` (the exact
warehouse `EDGARTOOLS_PROD_LOADER` has USAGE on, per
`08_loader_role.sql:73`), `SCHEMA` = `EDGARTOOLS_GOLD` (where
`PROCESS_RUN_MANIFEST_STREAM` lives), `DATABASE` = `EDGARTOOLS_PROD`. All
three prerequisites from the previous section are independently confirmed
against the actual secret this new caller would reuse — the "yes, zero
additional grants" conclusion below is not conditional.

**Adjacent but irrelevant footgun, noted for completeness only:**
`infra/scripts/deploy-snowflake-stack.sh:460-476` defaults its own
`DBT_SNOWFLAKE_ROLE` (used for `--run-dbt`, a *different* code path that
never touches `MDM_SNOWFLAKE_SECRET_JSON`) to the Terraform
`role_names.deployer` output (`EDGARTOOLS_PROD_DEPLOYER`), with an inline
comment warning "Running `--run-dbt` as-is will re-flip ownership of the
dynamic tables back to the deployer role." This is a live latent risk to
the *existing* manifest pipeline if that script is ever run against prod,
but it does not touch the secret this ticket's new caller would use, so it
does not affect sub-question 1's conclusion.

### Conclusion — sub-question 1

**Yes, confirmed: `EDGARTOOLS_PROD_LOADER`, via the existing
`MDM_SNOWFLAKE_SECRET_JSON` secret (the same secret/role `mdm export`/`mdm
sync-graph`/`mdm verify-graph` already use), can call `CALL
PROCESS_RUN_MANIFEST_STREAM()` directly today with zero additional
grants.** It already owns all three procedures in the call chain (so
`EXECUTE AS OWNER` resolves to its own privileges throughout, including the
nested calls), already has USAGE on `EDGARTOOLS_PROD` and
`EDGARTOOLS_GOLD`, and already has USAGE on the warehouse the secret
specifies — and the live secret's `ROLE`/`WAREHOUSE`/`SCHEMA`/`DATABASE`
fields (verified above) confirm all four match exactly. No new bootstrap
SQL is needed for this sub-question.

*Counterfactual, for completeness (not needed here):* if a *different*,
non-owning role were chosen instead, it would need at minimum:
```sql
GRANT USAGE ON DATABASE EDGARTOOLS_PROD TO ROLE <new_role>;
GRANT USAGE ON SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_GOLD TO ROLE <new_role>;
GRANT USAGE ON PROCEDURE EDGARTOOLS_PROD.EDGARTOOLS_GOLD.PROCESS_RUN_MANIFEST_STREAM() TO ROLE <new_role>;
GRANT USAGE ON WAREHOUSE EDGARTOOLS_PROD_REFRESH_WH TO ROLE <new_role>;
```
— but since the recommendation is to reuse `EDGARTOOLS_PROD_LOADER`, none of
this is actually required.

---

## The stream's fate — option 3 ("remove task/stream/schedule entirely") is only partly available

The ticket frames the task object, its underlying stream, and the schedule
as one bundle to decide the fate of together (all three named in the
question). They are not equally removable, and this matters directly for
evaluating option 3 ("Remove the task/stream/schedule from Terraform
entirely").

`PROCESS_RUN_MANIFEST_STREAM`'s body — the exact procedure the new
direct-connector-call design invokes — reads from the stream as its **only**
input (`04_refresh_wrapper.sql:218-221`):
```sql
c1 CURSOR FOR
    SELECT DISTINCT workflow_name, run_id
    FROM EDGARTOOLS_SOURCE.SNOWFLAKE_RUN_MANIFEST_STREAM
    WHERE METADATA$ACTION = 'INSERT';
```
and the row count driving its whole loop (line 225-231) is `COUNT(*)` over
that same stream query. There is no other code path in this procedure that
discovers which `(workflow_name, run_id)` pairs are pending — the stream
*is* the queue. Dropping `snowflake_stream_on_table.manifest` (the
Terraform resource backing `SNOWFLAKE_RUN_MANIFEST_STREAM`, referenced as a
`depends_on` for both `snowflake_execute.stream_processor_procedure`
(`main.tf:713-714`) and `snowflake_task.manifest_processor`
(`main.tf:753-755`)) would make `PROCESS_RUN_MANIFEST_STREAM()` process
zero rows on every call, regardless of who or what invokes it — silently
breaking the very trigger this whole map is designing, not just removing
dead weight.

**Conclusion: only the *task* and its *schedule* are cleanly removable
(or suspendable) under the new design — the *stream* must stay, because
it is the procedure's sole queue, not just the task's old wake-up
mechanism.** Whichever of options 2/3 is chosen for the task itself, the
stream (and `SNOWFLAKE_RUN_MANIFEST_STREAM`'s upstream producer — the
`SNOWFLAKE_RUN_MANIFEST_INBOX` table + whatever writes to it, out of scope
for this ticket) has to keep existing and keep being written to, or the
new direct-call trigger has nothing to process. This effectively narrows
the real decision to: task+schedule fully removed vs. task+schedule kept
suspended as a dormant fallback (options 2 vs. 3, restricted to the task
object only) — a clean "remove everything" is not on the table as written.

---

## Sub-question 2 — Can a task exist with no schedule for manual `EXECUTE TASK` fallback only?

### The claim under test

`infra/terraform/snowflake/modules/native_pull/main.tf:720-756` (resource
`snowflake_task.manifest_processor`, which provisions the live
`SNOWFLAKE_RUN_MANIFEST_TASK`). The comment in question, lines 730-734:
```
# Standalone task (no predecessor DAG) -- Snowflake requires an explicit
# schedule to resume/start one. This was previously unset here and only
# existed as out-of-band drift (`ALTER TASK ... SET SCHEDULE`) on the live
# dev task, so re-applying this module without it would strip the
# schedule from a `started` task and stop manifest processing.
```
Today the resource has `started = true` (line 725) and a `schedule { minutes
= 360 }` block (lines 749-751).

### What Snowflake's own docs say

**CREATE TASK** (docs.snowflake.com/en/sql-reference/sql/create-task) —
verbatim:
> "For [Triggered tasks], a schedule is not required. For other tasks, a
> schedule must be defined for a standalone task or the root task in a
> [task graph]; otherwise, the task only runs if manually executed using
> [EXECUTE TASK]."

and:
> "Newly created or cloned tasks are created suspended."

This directly confirms a standalone task **can** be created with no
schedule at all — the consequence is only that it won't run on its own; it
becomes manual-`EXECUTE TASK`-only, which is exactly the "dormant fallback"
shape the ticket is asking about. It also confirms the default state after
`CREATE TASK` is suspended regardless of schedule.

**EXECUTE TASK** (docs.snowflake.com/en/sql-reference/sql/execute-task) —
verbatim:
> "A suspended root task is run without resuming the task; there is no need
> to explicitly resume the root task before you execute this SQL command."

and, on privileges (verbatim, from the page's Usage Notes):
> "Executing a task requires either the OWNERSHIP or OPERATE privilege on
> the task. When the EXECUTE TASK command triggers a task run, Snowflake
> verifies that the role with the OWNERSHIP privilege on the task also has
> the USAGE privilege on the warehouse assigned to the task, as well as the
> global EXECUTE TASK privilege; if not, an error is produced."

This confirms: (a) `EXECUTE TASK` works on a **suspended** root/standalone
task directly, with no `RESUME` step required at all, regardless of whether
it has a schedule; (b) a caller needs either OWNERSHIP or OPERATE on the
task to invoke it manually; (c) the privilege checks Snowflake actually
enforces at execution time (warehouse USAGE, account-level EXECUTE TASK)
are checked against the task's **owner** role, not necessarily the
OPERATE-privileged caller — i.e. task execution, like the stored procedures
above, effectively runs under the owner's context.

**One nuance, worth naming but not load-bearing on the recommendation
below:** `ALTER TASK ... RESUME` (as opposed to `EXECUTE TASK`) on a
standalone task with no schedule and no predecessor is widely reported to
fail in real Snowflake (community/blog sources converge on this; I could
not pull a byte-for-byte error-string quote from a Snowflake-authored docs
page in this pass — the ALTER TASK reference page doesn't enumerate its
own runtime error conditions). This is likely the literal fact the
main.tf comment is gesturing at, and if so it's accurate as far as it
goes — but it's irrelevant to the dormant-fallback design here, because
that design never calls `RESUME` at all: it stays `started = false`
permanently and is invoked only via `EXECUTE TASK`, which (per the
verbatim quotes above) neither requires nor performs a resume. So this
nuance doesn't qualify the recommendation; it just explains why the
original comment reads the way it does.

**Also confirmed relevant for the fallback to actually be useful, not just
possible:** the task carries `when =
"SYSTEM$STREAM_HAS_DATA('${snowflake_stream_on_table.manifest.fully_qualified_name}')"`
(`main.tf:726`). Snowflake's CREATE TASK reference describes the `WHEN`
clause generically as evaluated "when a task is triggered" ("it validates
the conditions of the expression to determine whether to execute... If
[not met], the task skips the current run") without carving out an
exception for manual invocation, and `EXECUTE TASK`'s own reference
describes itself as "trigger[ing] ... a single run of a task" — i.e. an
`EXECUTE TASK` call is itself one of the trigger events the `WHEN`
description is written in terms of. No page states this with a single
unambiguous sentence, but nothing in either page's wording distinguishes
manual triggering from schedule/stream triggering for `WHEN` evaluation
purposes, and it is standard Snowflake tasks documentation to describe
`WHEN` as applying task-wide, not per-trigger-source. Practical
consequence for the dormant-fallback design: an operator pulling the
`EXECUTE TASK` lever would correctly get a no-op if the stream happens to
be empty at that moment, and correctly process whatever's pending if it
isn't — which is exactly the behavior wanted from a fallback (it processes
the same queue the direct-call trigger would have), not a risk to it. This
one point rests on converging documentation language rather than a single
explicit confirming sentence — worth a live smoke test (`EXECUTE TASK
SNOWFLAKE_RUN_MANIFEST_TASK` with an empty stream, confirm no
`REFRESH_AFTER_LOAD` call happens) before finalizing the fallback design,
but it is not a reason to expect the fallback wouldn't work.

### Is this representable in the Terraform resource itself?

`infra/terraform/snowflake/accounts/prod/versions.tf:5-9` pins
`snowflakedb/snowflake` provider `= 2.14.1`. That provider version's
`snowflake_task` resource schema (`docs/resources/task.md` at tag
`v2.14.1` in `snowflakedb/terraform-provider-snowflake`) lists `schedule`
as an **Optional** argument and `started` as a **Required** argument with
no default (must be explicitly `true` or `false`) — matching the
`CREATE TASK` semantics above exactly. So the "keep the task object,
suspend it, drop the schedule block" option is directly expressible:
```hcl
resource "snowflake_task" "manifest_processor" {
  database      = var.database_name
  schema        = var.gold_schema_name
  name          = var.manifest_task_name
  warehouse     = var.refresh_warehouse_name
  started       = false   # never RESUME'd; invoked only via manual EXECUTE TASK
  when          = "SYSTEM$STREAM_HAS_DATA('${snowflake_stream_on_table.manifest.fully_qualified_name}')"
  sql_statement = "CALL ${local.gold_schema_fqn}.${var.stream_processor_procedure_name}()"
  comment       = "Dormant manual-EXECUTE-TASK fallback; superseded by the direct connector-call trigger."
  # no schedule block
}
```
No Terraform provider-level obstacle to this shape.

### Conclusion — sub-question 2

**Yes — a task can be created/kept `started = false` with no `schedule`
block at all, and still be invoked on demand via `EXECUTE TASK` by a role
holding OWNERSHIP or OPERATE on it, with no RESUME step ever required.**
Snowflake's own CREATE TASK and EXECUTE TASK reference pages both confirm
this directly. The main.tf comment's literal framing ("requires an explicit
schedule to resume/start one") is imprecise — it is true only for `ALTER
TASK ... RESUME` (real, well-documented-in-practice restriction), not for
existence or for manual `EXECUTE TASK` invocation, which is unaffected by
whether a schedule is present. This means the ticket's middle option —
"keep the task object but stop its schedule, preserving it as a dormant
manual-fallback lever" — **is representable and functional**, not
foreclosed by any real Snowflake constraint. If that option is chosen,
whoever will manually pull the fallback lever needs OWNERSHIP or OPERATE on
the task. **Verified live** (`snow sql --connection edgartools-prod -q
"SHOW TASKS LIKE 'SNOWFLAKE_RUN_MANIFEST_TASK' IN DATABASE EDGARTOOLS_PROD;"`):
`owner: ACCOUNTADMIN` — confirming the prediction from this repo's own
established pattern (CLAUDE.md's "Streamlit-in-Snowflake ownership"
5-whys: "Terraform-created objects in this repo default to the admin role
as owner unless something has deliberately re-created them otherwise").
The task is `NOT` owned by `EDGARTOOLS_PROD_LOADER` — so if the
dormant-fallback design wants an operator to pull the lever using
`EDGARTOOLS_PROD_LOADER` (or any role other than `ACCOUNTADMIN`), that role
needs an explicit `GRANT OPERATE ON TASK
EDGARTOOLS_PROD.EDGARTOOLS_GOLD.SNOWFLAKE_RUN_MANIFEST_TASK TO ROLE
<role>;` — not needed if `ACCOUNTADMIN` (or whoever already holds
OWNERSHIP) is an acceptable operator identity for a rare manual fallback.
Same `SHOW TASKS` call also confirms the task's current live shape matches
what `main.tf` describes exactly: `warehouse: EDGARTOOLS_PROD_REFRESH_WH`,
`schedule: 360 MINUTE`, `state: started`,
`condition: SYSTEM$STREAM_HAS_DATA('EDGARTOOLS_PROD.EDGARTOOLS_SOURCE.SNOWFLAKE_RUN_MANIFEST_STREAM')`,
`definition: CALL EDGARTOOLS_PROD.EDGARTOOLS_GOLD.PROCESS_RUN_MANIFEST_STREAM()`
— no out-of-band drift from Terraform state as of this research pass.

---

## Sources

- Repo (read directly in this worktree):
  - `infra/snowflake/sql/bootstrap/04_refresh_wrapper.sql` (lines 19-22, 197-242) — `PROCESS_RUN_MANIFEST_STREAM`/`REFRESH_AFTER_LOAD` definitions
  - `infra/snowflake/sql/bootstrap/03_source_load_wrapper.sql` (lines 13-16) — `LOAD_EXPORTS_FOR_RUN` definition
  - `infra/snowflake/sql/bootstrap/08_loader_role.sql` (lines 39-44, 70-73, 180-191) — role, warehouse USAGE, ownership transfer of all three procedures
  - `infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql` — confirmed this is a different, unrelated apparatus (stale ticket file pointer)
  - `infra/terraform/snowflake/modules/native_pull/main.tf` (lines 720-756) — `snowflake_task.manifest_processor` resource and its schedule comment
  - `infra/terraform/snowflake/accounts/prod/versions.tf` (lines 5-9) — provider version pin (`snowflakedb/snowflake = 2.14.1`)
  - `edgar_warehouse/mdm/export.py` (lines 52-120) — `SnowflakeConnectionSettings`, secret field mapping, connector kwargs
  - `infra/scripts/bootstrap-prod-mdm.sh` (lines 311-333) — how `MDM_SNOWFLAKE_SECRET_JSON` is populated from `${NAME_PREFIX}/dbt/snowflake`
  - `infra/scripts/deploy-snowflake-stack.sh` (lines 457-476) — `DBT_SNOWFLAKE_ROLE`/`WAREHOUSE` default sourcing (flagged caveat)
  - `CLAUDE.md` — "Manifest-pipeline ownership + cursor-syntax incident", "MDM Snowflake mirror schema lost on cutover", "Streamlit-in-Snowflake ownership" 5-whys sections (live-verification history cited, not re-verified live in this pass)
- AWS (queried live in this pass, field-only extraction, no credentials printed):
  - `aws secretsmanager get-secret-value --secret-id edgartools-prod/mdm/snowflake` (account `690839588395`, `us-east-1`) — confirmed live `MDM_SNOWFLAKE_ROLE=EDGARTOOLS_PROD_LOADER`, `MDM_SNOWFLAKE_WAREHOUSE=EDGARTOOLS_PROD_REFRESH_WH`, `MDM_SNOWFLAKE_SCHEMA=EDGARTOOLS_GOLD`, `MDM_SNOWFLAKE_DATABASE=EDGARTOOLS_PROD`
- Snowflake (queried live via `snow sql --connection edgartools-prod` in this pass):
  - `SHOW TASKS LIKE 'SNOWFLAKE_RUN_MANIFEST_TASK' IN DATABASE EDGARTOOLS_PROD;` — confirmed live `owner=ACCOUNTADMIN`, `warehouse=EDGARTOOLS_PROD_REFRESH_WH`, `schedule=360 MINUTE`, `state=started`, `condition`/`definition` match `main.tf` with no drift
- Snowflake docs (fetched live in this pass):
  - https://docs.snowflake.com/en/sql-reference/sql/create-task — schedule requirement for standalone tasks; default suspended state; WHEN clause description
  - https://docs.snowflake.com/en/sql-reference/sql/execute-task — suspended-task execution without RESUME; OWNERSHIP/OPERATE privilege requirement; warehouse USAGE + account-level EXECUTE TASK check against the owner role; self-described as a trigger event
  - https://docs.snowflake.com/en/sql-reference/sql/alter-task — consulted; does not itself enumerate the RESUME-without-schedule error text
  - https://docs.snowflake.com/en/user-guide/tasks-intro — consulted for corroboration; confirms suspended-by-default framing, did not add new facts beyond CREATE TASK/EXECUTE TASK pages
  - https://docs.snowflake.com/en/user-guide/tasks-triggered — consulted for WHEN/manual-execution interaction; did not add facts beyond CREATE TASK's WHEN description
  - https://raw.githubusercontent.com/snowflakedb/terraform-provider-snowflake/v2.14.1/docs/resources/task.md — `snowflake_task` v2.14.1 schema: `schedule` Optional, `started` Required
  - Web search (community/blog sources, not a Snowflake-authored docs quote) corroborating that `ALTER TASK ... RESUME` on a schedule-less, predecessor-less standalone task fails at runtime, and corroborating that `WHEN` evaluation is not bypassed by manual `EXECUTE TASK` — both noted above as converging-evidence rather than single-quote-confirmed
