# 29 — Deploy the gated acquisition path to prod and dry-run it

**What to build:** Take the gated acquisition path (Tickets 13–19: Command
registration, the fenced ledger, the capture Facade, SEC-change-discovery
driving, retry-safety, ordered Logical Source Revisions, and the
filing-to-Silver acceptance seam) from "merged to `main`, verified locally
against ephemeral Postgres" to "live in prod and observed processing a real
diff end-to-end" — for the one source family already wired through it
(`filing_artifact`). Not a rebuild of anything already decided; this is the
first real deployment of code this map already produced.

**Blocked by:** 18 — Materialize ordered logical source revisions; 19 —
Complete the filing-to-Silver acceptance seam; 31 — `EXCLUDED_OPERATIONAL_TABLES`
content never reaches canonical silver once canonical exists (added after
the live dry-run attempt surfaced it as the actual remaining blocker)

**Status:** ready-for-agent

- [ ] `013_acquisition_ledger.sql` (and its widened `finalize_source_fetch`
  signature from Ticket 17) is applied to prod's MDM Postgres via the
  standard `mdm migrate` path — not ad hoc — and confirmed live (no
  `UndefinedColumn`/`UndefinedTable` on a real query), following the
  lesson in CLAUDE.md's "MDM Postgres migration-011 schema drift" incident:
  verify against the *current*, non-orphaned state machine, not a stale one.
- [ ] Warehouse and MDM images are rebuilt from current `main` and pushed to
  ECR (per CLAUDE.md's image-rebuild table — this path touches both
  `edgar_warehouse/acquisition/**` and, if `mdm/**` changed since the last
  prod image, that role too) and deployed via `deploy-aws-application.sh
  --env prod`.
- [ ] A real `drive-filing-discovery-for-date` (or the Command-registration
  seam's equivalent entry point) runs against prod for a bounded, small
  date/CIK scope — not the full universe — and is observed producing: a
  Fetch Decision per candidate, a verified Bronze capture, a materialized
  Logical Source Revision, and a Silver acceptance outcome, traceable
  end-to-end via the ledger's own status/observation-position reads.
  Chosen scope is small enough to inspect every row by hand.
  <!-- decision: which command is the real prod entry point once Command
       registration expands, and what the dry-run's exact bounded scope
       is, are resolved during this ticket, not pre-decided here -->
- [ ] A no-op replay of the same scope is run a second time and confirmed to
  change nothing new (idempotent convergence, one of the map's acceptance
  criteria) — the first live proof of that criterion against real prod
  infrastructure rather than a test double.
- [ ] Any prod-only gap found in the process (grants, orphaned state
  machines, stale secrets — this repo's history says to expect at least
  one) is fixed via a committed, re-runnable script, not a manual one-off,
  per the standing "no state survives an account rebuild unless it's
  Terraform or a script" lesson in CLAUDE.md.
- [ ] Legacy acquisition paths for `filing_artifact` are left untouched —
  this ticket proves the new path works in prod, it does not cut traffic
  over or remove the old path (that's Ticket 27, and only after every
  source family, not just this one, proves out).

## Answer (partial — dry run blocked, see below)

**Done:**

- [x] Migration 013 applied to prod MDM Postgres via `edgartools-prod-mdm-utility`
  (`{"mode": "mdm_migrate"}`, the current, non-orphaned consolidated machine —
  confirmed *not* one of the orphaned per-command originals per CLAUDE.md's
  "MDM Postgres migration-011 schema drift" lesson). Verified live: all six
  `edgartools_acquisition_*` roles exist, `application` holds `SET TRUE`
  non-inherited membership in five of them, `SET ROLE
  edgartools_acquisition_processor` successfully reads `source_fetch_decision`,
  and none of the nine acquisition objects carry a direct `application` grant.
  Two genuine, previously-undiscovered prod-only provisioning bugs were found
  and fixed live along the way (PR #453, merged): (1)
  `bootstrap-prod-mdm.sh`'s post-migrate fencing `REVOKE`s ran as
  `snowflake_admin` *after* ownership of the acquisition objects had already
  moved to `edgartools_acquisition_owner` inside the same script's `mdm
  migrate` call, failing with `permission denied for table` — fixed with `SET
  ROLE edgartools_acquisition_owner` around just those statements; (2) all
  four `bootstrap-*`/`remove-aws-mdm-rds-after-cutover.sh` scripts' shared
  `aws_cli()` helper hit bash 3.2's empty-array-under-`set -u` unbound-variable
  bug on macOS (same class as CLAUDE.md's documented `mapfile`/`mktemp`
  issues) — fixed with the `${args[@]+"${args[@]}"}` idiom in all four.
- [x] Warehouse and MDM images rebuilt from current `main` (digests
  `sha256:0fbb4645...` / `sha256:77a4ceb7...`) and deployed via
  `deploy-aws-application.sh --env prod --enable-mdm`; all task defs and
  state machines re-registered onto them, confirmed via the written manifest.
- [x] Prod-only gaps fixed via committed, re-runnable scripts, not manual
  one-offs (the two `bootstrap-prod-mdm.sh`/`aws_cli()` fixes above).
- [x] Legacy `filing_artifact` acquisition paths untouched — nothing in this
  ticket's work modified `capture-filing-artifact` or any pre-Ticket-13 path.

**Blocked — not done:**

- [ ] The bounded live dry run (Fetch Decision → Bronze capture → Logical
  Source Revision → Silver acceptance, traceable end-to-end) and its no-op
  replay were **not achieved**. Seeding one business date
  (`load-daily-form-index-for-date 2026-08-21`, 3,719 total daily-index rows)
  succeeded at the ECS-task level but its own log showed
  `"skipped": true, "tables_merged": []` for the silver-database publish
  step — the write never reached canonical. A follow-up
  `drive-filing-discovery-for-date 2026-08-21` run against prod then failed
  closed exactly as designed: `WarehouseRuntimeError: No sealed discovery
  observation for business_date=2026-08-21 (checkpoint status='missing')`,
  since canonical genuinely had no sealed checkpoint for that date.
- Root-caused to two independent, compounding bugs in the general silver
  merge/publish subsystem — **neither caused by this ticket's own diff**,
  both pre-existing and newly discovered while attempting the dry run:
  1. `compute_silver_fingerprint`'s skip-if-unchanged optimization
     (`silver_protection.py`) only fingerprints `PROTECTED_TABLE_REGISTRY`
     tables. `load-daily-form-index-for-date` writes exclusively to
     `EXCLUDED_OPERATIONAL_TABLES` members (`stg_daily_index_filing`,
     `sec_daily_index_checkpoint`), so its fingerprint is *always* identical
     to hydration's, and the publish is skipped every single time,
     unconditionally.
  2. Deeper and more consequential, found while investigating fix #1:
     `merge_candidate_into_canonical`'s only content-copying loop iterates
     exclusively over `PROTECTED_TABLE_REGISTRY` — `EXCLUDED_OPERATIONAL_TABLES`
     tables are *never* copied from candidate into the merged output once
     canonical already exists (only the very first, canonical-doesn't-exist-yet
     publish uploads a local file as-is, with no merge involved at all). This
     contradicts the exclusion's own documented intent ("a candidate is
     always free to overwrite them") and is not something fix #1 alone
     resolves — fixing only the fingerprint would stop the false "skipped"
     signal but the merge would still silently fail to persist the excluded
     tables' content.
- Filed as [31 — `EXCLUDED_OPERATIONAL_TABLES` content never reaches canonical
  silver once canonical exists](31-excluded-operational-tables-never-reach-canonical-silver.md)
  (blocks this ticket's remaining checkboxes) and
  [30 — Fence `application` from acquisition ledger tables under Snowflake
  Postgres's `snowflake_write` role](30-fence-application-from-acquisition-tables-under-snowflake-write.md)
  (a separate, non-blocking finding: `application` has ambient read/write
  access to the fenced acquisition tables via inherited membership in
  Snowflake Postgres's own managed `snowflake_write` role, bypassing
  migration 013's explicit per-object `REVOKE`s — confirmed live via
  `has_table_privilege`; `models.py`'s `SourceExpectedProducerRecord`
  docstring's "sole enforcement layer" claim is false in prod today until
  30 is resolved).
- Deliberately **not fixed in this session**: both newly-found bugs touch
  shared, high-blast-radius infrastructure (the general silver merge/publish
  path used by every silver-writing command in the platform, and a managed
  Postgres platform role's default membership) — rushing a fix under
  production time pressure risked a worse outcome than leaving the dry run
  incomplete for a follow-up session with a clean, well-tested change.

**Status:** ready-for-agent (remains open — reopen once 31, and optionally
30, are resolved, then repeat the seed → drive → replay sequence above).
