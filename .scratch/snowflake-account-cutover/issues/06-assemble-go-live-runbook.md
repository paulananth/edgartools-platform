# Assemble the documented go-live runbook, driven by go-live.sh

Type: grilling
Status: resolved

Blocked by: 01, 05, 07

## Question

This map's terminal deliverable. Given Ticket 01's grants-ordering fix and
Ticket 05's repopulation sequence decision, assemble the concrete,
documented procedure for taking a brand-new Snowflake account fully live —
explicitly built around `infra/scripts/go-live.sh` (per the user's explicit
requirement that this be clearly documented, including how to run it via
go-live.sh, not a bespoke one-off script).

Resolve: does the repopulation sequence from Ticket 05 become a new
`go-live.sh` stage (consistent with how every other stage already works),
or does it stay a documented manual step run after the wizard's existing
stages complete? Where the gold-verify command (already decided on the
snowflake-env-provisioning map's Ticket 06, not yet implemented) plugs into
this sequence. What the final runbook doc looks like and where it lives
(a new doc under `docs/`, or a section added to an existing one like
`docs/runbook.md`).

## Notes

`grilling`-type — assembling a runbook from already-decided pieces still
involves real sequencing/placement judgment calls (new stage vs. documented
manual step chief among them).

This ticket does not itself run the actual cutover — per this map's Notes,
execution happens in a later "implement ticket NN"-style session once this
decision locks, mirroring the pattern used on the snowflake-env-provisioning
map.

## Answer

Resolved via `/grilling` with the user driving the map. Read `go-live.sh`'s
actual `build_stages()` in full (lines 620-800, 15 stages today) and traced
several real dependency edges directly in code before asking anything, since
placement questions need real constraints, not guesses.

### Four decisions

**1. `seed-universe` (unscoped) becomes its own new stage, placed
immediately after "Snowflake: native-pull foundation."** Two hard
constraints bound the window: `mdm seed-universe` (already called inside
the "MDM + graph: connectivity..." stage) errors ("silver universe empty;
warehouse seed-universe must run first") unless the warehouse-level
`seed-universe` ran first — so the new stage must precede it. Snowpipe
(created by native-pull foundation) only auto-ingests S3 objects created
*after* the pipe exists, not pre-existing ones — so the new stage must
follow native-pull foundation, or its export manifest sits unprocessed
until someone manually triggers a pipe refresh. The user chose the early
end of that window (right after native-pull foundation) over the late end
(right before the MDM stage), to give Snowpipe's few-minutes ingest lag the
most runway before anything downstream needs the data.

**2. The old bounded `seed-universe --limit 100` line inside "Data: bounded
smoke only" is removed**, not kept as a redundant double-check. Once the
new unscoped stage runs earlier in the sequence, it's pointless duplicate
SEC-feed work that would also write a second, competing `TICKER_REFERENCE`
export manifest under a different `run_id`. `bootstrap-next --limit 100`
stays in that stage — it doesn't depend on the removed line, since tracking
status is already seeded by the new stage.

**3. `gold verify-live` (design already locked on the snowflake-env-
provisioning map's Ticket 06, not yet implemented) is appended to the
existing "Snowflake: standalone gold-refresh" stage**, replacing its
current manual `echo "...verify row counts in EDGARTOOLS_GOLD before
treating gold as current"` reminder with an actual automated, fail-closed
check — fail-fast, before the MDM+graph stages spend time on identity
resolution/graph sync against a gold layer that turned out empty. Rejected:
a brand-new stage at the very end of the whole sequence (would report the
same failure much later, after unrelated stages already ran).

**4. `docs/runbook.md` is restructured in place, not replaced by a second
doc.** Found it predates `go-live.sh` entirely — 886 lines of raw manual
Terraform/AWS CLI steps (Step 1-8), never mentions `go-live.sh` once, but
still carries genuinely valuable content (a "Gotchas and Known Issues"
section, a "Recovering from a partial load_history failure" section) that
shouldn't be duplicated into a second doc. Decision: prepend a new "Quick
Path — install.sh (recommended)" section presenting the stage-driven flow
below, and demote the existing manual Step 1-8 content to a "Manual / Under
the Hood" reference section beneath it, kept for when a specific stage
fails and someone needs its underlying commands by hand. One doc, one
source of truth — this repo has already been bitten more than once
(manifest-pipeline Terraform/SQL drift, the bootstrap-SQL/Terraform drift
Ticket 07 found) by two competing copies of the same procedure silently
diverging.

### Two corrections surfaced while tracing the above (fixed in their
original tickets, not restated in full here)

- **Ticket 05** overstated why `seed-universe` needs to run unscoped —
  `TICKER_REFERENCE` is actually exported in full regardless of `--limit`
  (captured before the limit slice, `warehouse_orchestrator.py:1692-1693`).
  The real reason is `bootstrap_pending` tracking-status completeness for
  newly-discovered CIKs. The decision (unscoped, early) is unchanged.
- **Ticket 04**'s "you need a second AWS access-roles stage" finding was
  wrong. `deploy-snowflake-stack.sh` (called by stage 7) already does its
  own internal AWS↔Snowflake reconciliation in one pass — apply AWS access
  with a bootstrap-trust overlay, apply Snowflake storage-integration-only
  to emit the real subscriber ARN, **re-apply** AWS access with that real
  ARN via an explicit `-var` (confirmed this wins over the remote-state
  fallback: `access/aws/accounts/prod/main.tf:36`), then the full Snowflake
  stack, then the Snowflake access root. The drift I observed earlier was
  an artifact of testing with a bare `terraform plan` outside this script,
  before the new account had anything to reconcile against — not a real gap
  in the sequence. No new stage needed for this.

### Also resolved here: Ticket 03's placement question

Ticket 03 explicitly deferred its own placement decision to this ticket.
Resolved: the 3-command MDM schema/Postgres-provisioning sequence
(`CREATE SCHEMA IF NOT EXISTS {db}.MDM`, then
`mdm_create_network_policy.sql`, then `mdm_create_instance.sql`) is
prepended to the start of the existing "Snowflake Postgres / graph
prerequisites" stage, ahead of its current `bootstrap-prod-mdm.sh` call —
which needs the instance already `READY`. This finally uses the
`mdm_schema_name_q`/`mdm_network_policy_name_q`/`mdm_network_rule_name_q`
variables `go-live.sh` already computes but has never referenced (dead
scaffolding Ticket 03 found).

### Final stage sequence (18 stages, was 15 — `go-live.sh` to be renamed
`install.sh` per Ticket 05; new/changed stages marked)

1. AWS: Terraform state bucket
2. Snowflake: Neo4j Native App install
3. AWS: passive infrastructure
4. AWS: access roles/policies
5. AWS: ECR image publish
6. AWS: ECS task definitions and Step Functions
7. Snowflake: native-pull foundation — **also carries Ticket 07's `01`/
   `03`/`04` backport** (folded into the Terraform templates this stage
   applies, per Ticket 07's decision to keep one source of truth rather than
   a competing raw-SQL stage)
8. **NEW — AWS/silver: `seed-universe` (full/unscoped)**
9. **NEW — Snowflake: MDM export targets** (`07_mdm_export_targets.sql`,
   Ticket 07) — must precede the next stage, since `company.sql` (dbt)
   reads `mdm_export.MDM_COMPANY_ENTITY`
10. Snowflake: dbt gold
11. **NEW — Snowflake: loader role ownership** (`08_loader_role.sql`,
    Ticket 07) — must run after dbt gold creates the dynamic tables it
    transfers ownership of, and before any `REFRESH_AFTER_LOAD` call
    (stages 14/15 below), since that requires the direct owner role
12. Snowflake: Streamlit dashboard
13. Snowflake Postgres / graph prerequisites — **prepend the 3-command MDM
    schema/instance provisioning sequence** (Ticket 03, this ticket)
14. AWS: `bronze_seed_silver_gold` (one-click data refresh)
15. Snowflake: standalone gold-refresh — **append `gold verify-live`**
    (this ticket, decision 3)
16. MDM + graph: connectivity, migrations, sync, verification — leads with
    the Neo4j grants SQL (Ticket 01, already decided)
17. MDM + graph: AWS MDM E2E/status checks
18. Data: bounded smoke only — **`seed-universe --limit 100` line removed**
    (this ticket, decision 2); `bootstrap-next --limit 100` unchanged

This is the map's terminal ticket. No tickets remain open.

## Implementation (2026-08-07)

Implemented in full, per the user's explicit choice of "full map
implementation" scope (including Ticket 07's Terraform backport and
building `gold-verify-live`, not just the stage restructuring). Summary:

- `go-live.sh` renamed to `install.sh` (file, workspace dir, env vars,
  terminology throughout); `tests/architecture/test_go_live_wizard.py`
  renamed/updated to `test_install_wizard.py`, 25/25 passing.
- All 18 stages landed exactly as decided above (seed-universe unscoped
  with `WAREHOUSE_RUNTIME_MODE=bronze_capture` -- not
  `infrastructure_validation`, a real correction found during
  implementation, see Ticket 05's file; MDM export targets; loader role
  ownership; Neo4j grants moved; MDM schema/Postgres prepend; redundant
  smoke-test line removed).
- `edgar-warehouse gold-verify-live` built (`edgar_warehouse/serving/
  gold_verify.py` + CLI wiring), checking all 21 current
  `EDGARTOOLS_GOLD` dynamic tables (not 20 -- `ADV_FUND_COUNT_RECONCILIATION`
  was missing from both `04_refresh_wrapper.sql` and `08_loader_role.sql`'s
  lists, fixed in both as part of this pass). Wired into the gold-refresh
  stage as a poll loop (20 attempts, 60s apart), not a fixed sleep.
- Ticket 07's Terraform backport done: `01_source_stage.sql`'s 9 missing
  tables added to `native_pull`'s `table_definitions`; `03`/`04`'s current
  procedure bodies (not just table lists -- a real body-level diff found
  additional drift in both) backported into `source_load_procedure.sql`/
  `refresh_procedure.sql`. Verified via `terraform validate`/`fmt` plus an
  independent second-pass mechanical column/key diff against the DDL --
  all 9 tables' columns, types, and nullability match exactly.
- `docs/runbook.md`: new "Quick Path -- install.sh" section prepended;
  existing manual steps demoted under a new "Manual / Under the Hood"
  heading, kept verbatim.
- Two prior-ticket corrections made while implementing: Ticket 05's stated
  rationale for unscoped seed-universe was wrong in two ways (fixed in its
  file); Ticket 04's "second AWS access-roles stage" finding was wrong --
  `deploy-snowflake-stack.sh` already self-reconciles (fixed in its file).
- Full test suite green (1885 passed, 4 skipped) after fixing 3
  architecture-test assumptions that didn't yet know about
  `gold-verify-live` bypassing the warehouse orchestrator (same documented
  precedent as the existing `migrate-silver-shards` exclusion).
- One incident during implementation: a syntax-check command accidentally
  executed against the live `edgartools-prod` Snowflake connection (4
  harmless session-scoped `SET` statements, then errored out at `USE
  DATABASE` before any real DDL ran -- no data created/modified/deleted).
  Caught immediately, flagged to the user, switched to offline fakebin
  verification for the rest of the session.
- Not committed -- awaiting the user's explicit go-ahead per this repo's
  git-commit convention.
