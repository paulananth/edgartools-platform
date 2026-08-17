# Decide Invocation Plumbing and the Fate of SNOWFLAKE_RUN_MANIFEST_TASK

Type: research
Status: resolved

## Question

Round 2 settled that invocation is a direct Snowflake connector call
(`CALL PROCESS_RUN_MANIFEST_STREAM()`), not `EXECUTE TASK` against the
existing `snowflake_task.manifest_processor` object
(`infra/terraform/snowflake/modules/native_pull/main.tf:719-750`). Two
things that decision leaves open:

1. **Credential plumbing**: whatever compute runs the connector call
   (see [ticket 02](02-design-idle-detection-recheck-and-race-safety.md)'s
   Lambda-vs-ECS question) needs Snowflake credentials. This repo already
   has a live pattern for exactly this — `MDM_SNOWFLAKE_SECRET_JSON`, read
   by `mdm export`/`mdm sync-graph`/`mdm verify-graph`, all authenticating
   as `EDGARTOOLS_PROD_LOADER` (see CLAUDE.md's "Manifest-pipeline
   ownership + cursor-syntax incident" and "MDM Snowflake mirror schema
   lost on cutover" 5-whys for the role's provenance and grant history).
   Confirm whether that same secret/role can be reused as-is for this new
   caller, or whether `PROCESS_RUN_MANIFEST_STREAM` requires a role with
   different grants than `EDGARTOOLS_PROD_LOADER` already has (research:
   read the procedure's actual `EXECUTE AS` clause and grants in
   `infra/snowflake/sql/bootstrap/`).
2. **What happens to `snowflake_task.manifest_processor` (the task
   object), its underlying stream, and the Terraform-managed `schedule {
   minutes = 360 }` block?** Three options, in increasing order of
   removal:
   - Leave the task/stream/schedule entirely as-is, running alongside the
     new direct-call trigger as an unplanned second path (NOT
     recommended — defeats "replace the poll entirely," and now two
     things can call the same non-idempotent-by-assumption procedure).
   - Keep the task object but stop its schedule (`ALTER TASK ... SUSPEND`
     equivalent in Terraform), preserving it as a dormant manual-fallback
     lever (`EXECUTE TASK` by an operator) without it running on its own.
   - Remove the task/stream/schedule from Terraform entirely, since the
     stream-triggered task pattern becomes fully redundant once
     something else calls the procedure directly.
   Note the existing comment at `main.tf:731-734`: Snowflake requires an
   explicit `schedule` block to resume/start a standalone task at all —
   confirm whether a task can exist with **no** schedule (started=false,
   purely available for manual `EXECUTE TASK`) before assuming the
   "keep as dormant fallback" option is even representable in Terraform.

## Answer

Full research: [03-invocation-plumbing-findings.md](../research/03-invocation-plumbing-findings.md)
(live-verified against both the repo and the actual AWS/Snowflake account —
not desk research).

**1. Credential plumbing: reuse `EDGARTOOLS_PROD_LOADER` via
`MDM_SNOWFLAKE_SECRET_JSON` as-is — zero new grants needed.**
`PROCESS_RUN_MANIFEST_STREAM` actually lives in
`infra/snowflake/sql/bootstrap/04_refresh_wrapper.sql:197-242` (the ticket's
own file pointer, inherited from CLAUDE.md, was stale — `13_silver_landing_ingest.sql`
was reused later for an unrelated apparatus). It and the two procedures it
calls internally (`LOAD_EXPORTS_FOR_RUN`, `REFRESH_AFTER_LOAD`) are all
`EXECUTE AS OWNER` and all owned by `EDGARTOOLS_PROD_LOADER`
(`08_loader_role.sql:180-191`) — so the identity of whoever issues the
outermost `CALL` only needs USAGE on the database/schema and the warehouse,
plus resolve access to the procedure (automatic for its owner). Live-verified
the actual `edgartools-prod/mdm/snowflake` secret
(`aws secretsmanager get-secret-value`, field-only extraction):
`ROLE=EDGARTOOLS_PROD_LOADER`, `WAREHOUSE=EDGARTOOLS_PROD_REFRESH_WH`,
`SCHEMA=EDGARTOOLS_GOLD`, `DATABASE=EDGARTOOLS_PROD` — exactly what's
needed, already in place. The new ECS command (per
[ticket 02](02-design-idle-detection-recheck-and-race-safety.md)'s
compute decision) reuses this secret unchanged, same pattern as `mdm export`/
`mdm sync-graph`/`mdm verify-graph`.

**2. Task fate: remove `snowflake_task.manifest_processor` and its schedule
from Terraform entirely. The stream stays — it's not part of this
decision.** The research found `PROCESS_RUN_MANIFEST_STREAM`'s body reads
`SNOWFLAKE_RUN_MANIFEST_STREAM` as its *sole* queue
(`04_refresh_wrapper.sql:218-231`) — there's no other way it discovers
pending `(workflow_name, run_id)` pairs, so dropping the stream would zero
out every future call regardless of invoker. That narrows the real decision
to the task object alone, and the answer is to remove it (not keep it
suspended as a dormant fallback):

- The loader role can already `CALL PROCESS_RUN_MANIFEST_STREAM()` directly
  with zero new grants (point 1 above) — manual break-glass capability
  doesn't depend on keeping the task object; an operator runs
  `snow sql --connection edgartools-prod -q "CALL EDGARTOOLS_GOLD.PROCESS_RUN_MANIFEST_STREAM();"`
  instead of `EXECUTE TASK`.
- Removing it removes an entire incident class this repo has already hit
  twice on this exact object: the "SNOWFLAKE_RUN_MANIFEST_TASK suspension"
  root-cause (ticket 99) and the "Dev Terraform/Snowflake go-live blockers"
  5-whys (schedule block missing from Terraform history, live drift). One
  fewer Terraform-managed object with a schedule to silently drift.
- Confirmed representable and functional either way, so this wasn't a
  constraint-driven choice: Snowflake's own CREATE TASK/EXECUTE TASK docs
  (quoted verbatim in the findings) confirm a suspended, schedule-less task
  can be invoked via `EXECUTE TASK` with no `RESUME` ever required — so
  "keep it as a dormant fallback" was fully available, just not chosen.
  The `main.tf:730-734` comment's framing ("requires a schedule to
  resume/start") is imprecise — true only for `ALTER TASK ... RESUME`, not
  for existence or manual invocation — worth correcting when the Terraform
  is actually edited, though that's implementation, not this ticket.
- Live-verified the task is currently owned by `ACCOUNTADMIN`, not
  `EDGARTOOLS_PROD_LOADER` (`SHOW TASKS`) — moot now that it's being
  removed rather than kept as a loader-operated fallback, but would have
  needed `GRANT OPERATE ON TASK ... TO ROLE EDGARTOOLS_PROD_LOADER` if kept.

**Addendum (Opus design-review pass, finding G6 — see
[DESIGN-SUMMARY.md](../DESIGN-SUMMARY.md)):** the removed task carries a
`when = "SYSTEM$STREAM_HAS_DATA('...SNOWFLAKE_RUN_MANIFEST_STREAM')"`
guard (`main.tf:726`, live-confirmed in the research's `SHOW TASKS`
output) that this Answer didn't account for. That guard is what keeps the
6-hour timer from resuming the warehouse when there's nothing to do. The
new direct-`CALL` design has no equivalent guard — every fire resumes
`EDGARTOOLS_PROD_REFRESH_WH` (60s minimum billing) unconditionally,
including fires after a FAILED/ABORTED execution that produced no
manifest at all. [Ticket 01](01-decide-once-per-day-debounce-cap-semantics.md)'s
"cheap no-op" finding is true in *procedure* terms (the SQL body does
almost nothing on an empty stream) but doesn't cover the warehouse
wake-up cost, which this map's own stated goal ("no wasted wake-ups," see
map.md's Notes) does care about. Not re-opening this ticket's decision —
the task is still being removed — but implementers should treat the
warehouse-wake-up count as something to measure post-cutover against the
old 6-hour baseline (see DESIGN-SUMMARY.md §5), not assume it strictly
improves.
