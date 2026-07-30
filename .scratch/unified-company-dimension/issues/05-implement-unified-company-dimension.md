# 05 — Implement unified COMPANY dimension

Type: task
Status: claimed
Labels: needs-triage
Blocked by: 01, 02, 03, 04

## Question / work

Implement Option B per resolved design in
`.scratch/unified-company-dimension/spec.md` and map decisions 01–04.

**Do not start until operator explicitly claims this ticket.**

## Scope (from design)

1. Enrich `EDGARTOOLS_GOLD.COMPANY` (dbt or agreed path): left join MDM by CIK;
   PK remains `company_key`; add `entity_id`, `display_name` (MDM-preferring),
   explore/ops columns (`tracking_status`, `parent_company_entity_id`, flags).
2. Replace physical `GOLD.MDM_COMPANY` with compatibility view/projection.
3. Migrate known readers; stop dual `mdm export` MERGE to GOLD.MDM_COMPANY.
4. Drop compat view after soak.
5. Agent Decision Surface: **no** `entity_id` / tracking / parent as Decision
   Features.

## Out of scope

- Graph `MDM` schema mirror redesign (unless unblocked separately).
- Person/security/fund/adviser unify.
- Residual holds pipeline.

## Acceptance

- Single CIK-keyed `COMPANY` with entity_id attribute.
- Filing gold joins still on `company_key`.
- Compat path for `MDM_COMPANY` during migration; dual export stopped.
- No agent-contract expansion of entity_id without a new ADR.

## Progress (2026-07-29)

**Code/config complete and locally verified for steps 1–4; not yet applied to
live Snowflake.** All changes are file edits in this branch, fully reversible:

- `edgar_warehouse/mdm/export.py`: `DOMAIN_TO_TABLE["company"]` renamed to
  `MDM_COMPANY_ENTITY` per ticket 06. Found and fixed a second circularity
  ticket 06 didn't anticipate: `_mirror_entity_ids()` used the *same* table
  name for both the GOLD writer and the MDM-schema graph-sync mirror
  (`snowflake_graph.py` still hardcodes the literal `"MDM_COMPANY"` for that
  mirror). A global rename would have made `mdm export` MERGE into a
  nonexistent `MDM.MDM_COMPANY_ENTITY` (hard failure, not silent — writer never
  creates its target) and desynced sync-graph. Fixed with a new
  `DOMAIN_TO_MIRROR_TABLE` override map (company only; every other domain
  unaffected) — GOLD gets `MDM_COMPANY_ENTITY`, the MDM mirror keeps
  `MDM_COMPANY`. Locked in by
  `test_company_gold_and_mirror_targets_diverge_by_design` in
  `tests/mdm/test_export.py`.
- `infra/snowflake/sql/bootstrap/07_mdm_export_targets.sql`: guarded
  `ALTER TABLE ... RENAME` (not a bare rename — confirmed live against prod
  scratch objects that a bare `ALTER TABLE IF EXISTS` (a) errors on any re-run
  once the target name exists, and (b) does not check object type, so it
  would happily rename the future compat *view* too instead of no-opping).
  Guard is an `EXECUTE IMMEDIATE` Snowflake Scripting block checking
  `INFORMATION_SCHEMA.TABLES` first — verified live, safe to re-run
  indefinitely. Also adds a direct `GRANT SELECT ... TO ROLE
  $loader_role_name` — confirmed live that `EDGARTOOLS_PROD_LOADER` (the role
  `company.sql`'s dynamic table runs as) had **zero** existing grant on
  `MDM_COMPANY`/`MDM_COMPANY_ENTITY`, which would have failed
  `--full-refresh` the same way CLAUDE.md's documented
  `EDGARTOOLS_DEV_DEPLOYER`/`EDGARTOOLS_SOURCE` incident did.
- `infra/snowflake/dbt/edgartools_gold/models/sources.yml`: new `mdm_export`
  source (separate from `edgartools_source` — different write mechanism, see
  ticket 06) pointing at `MDM_COMPANY_ENTITY`.
- `infra/snowflake/dbt/edgartools_gold/models/gold/company.sql`: left join
  adds `entity_id`, `display_name` (MDM-preferring), `tracking_status`,
  `parent_company_entity_id`, and `has_multi_match_mdm_entity` (ticket 02's
  flag safeguard — `row_number()`/`count()` over cik, 0 live cases today per
  ticket 05's research findings, kept for a future re-run of MDM entity
  resolution). Compiled successfully against the prod target (`dbt compile
  --target prod --select company` — fully-qualified names resolved
  correctly).
- New model `infra/snowflake/dbt/edgartools_gold/models/gold/mdm_company.sql`:
  the compat view (step 2), materialized as a plain `view` aliased
  `MDM_COMPANY` — a byte-for-byte 15-column projection of
  `MDM_COMPANY_ENTITY` (not routed through enriched `COMPANY`, since
  `COMPANY` doesn't carry `ein`/`ticker`/`primary_ticker`/`primary_exchange`/
  `valid_from`/`valid_to` and ticket 04 explicitly allows "thin projection
  matching old column names where possible" as an alternative to a
  COMPANY-routed view). Confirmed live: `EDGARTOOLS_GOLD` already has a
  standing `SELECT ON FUTURE VIEW` grant to `EDGARTOOLS_PROD_READER`, so this
  new view needs no separate grant statement. Also confirmed via grep: no
  in-repo Python reader (dashboards included) references `MDM_COMPANY`
  directly today, so step 3 ("migrate known readers") is a no-op to state,
  not execute.
- Full local test suite: 1394 passed, 4 skipped (was 1393/4 before this
  ticket; +1 new regression test). `dbt compile` clean for both changed/new
  models against the prod target.

## Progress (2026-07-29, continued — applied to prod)

Operator confirmed applying to prod now (daily_incremental deferred separately).
Applied and verified live:

1. `07_mdm_export_targets.sql` applied to prod via `snow sql`. Guarded rename
   fired correctly (`target_exists=0` → executed the `ALTER TABLE RENAME`).
   Verified: `MDM_COMPANY_ENTITY` has all 32,970 original rows, `OWNERSHIP`
   still `ACCOUNTADMIN`, `SELECT` still granted to `EDGARTOOLS_PROD_READER`
   (both carried across the rename as expected), plus the new `SELECT` grant
   for `EDGARTOOLS_PROD_LOADER`.
2. `dbt run --target prod --select company mdm_company --full-refresh`.
   `company` succeeded first try. `mdm_company` (the new compat view)
   **failed** the first attempt: `EDGARTOOLS_PROD_LOADER` had `CREATE DYNAMIC
   TABLE`/`CREATE PROCEDURE`/`CREATE TASK` on `EDGARTOOLS_GOLD` but never
   `CREATE VIEW` — no plain view had ever been created there before, so this
   gap was invisible until now. Fixed at the root: added `GRANT CREATE VIEW
   ON SCHEMA ... TO ROLE $loader_role_name` to `08_loader_role.sql` (not just
   applied ad hoc), then applied that one grant live and re-ran. Both models
   now `SUCCESS` in prod.
3. Verified live: `EDGARTOOLS_GOLD.COMPANY` — 32,970 rows, all 32,970 with a
   joined `entity_id`, 0 `has_multi_match_mdm_entity` (matches this ticket's
   research findings — clean 1:1 join, safeguard flag present but not
   exercised). `EDGARTOOLS_GOLD.MDM_COMPANY` (compat view) — 32,970 rows,
   reading through to `MDM_COMPANY_ENTITY` correctly.
4. `mdm export`'s next scheduled run will exercise the renamed target
   end-to-end (not separately triggered this session — no pending change-log
   rows required it). Not yet independently confirmed; low risk given the
   direct-grant and dry compile checks already passed.

**Still open:** step 4 (drop the compat view after a soak period) — soak
length still undecided, tracked in the map's "Not yet specified". Nothing
else in ticket 05's scope remains unapplied.
