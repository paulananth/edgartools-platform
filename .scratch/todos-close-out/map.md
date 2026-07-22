# TODOS.md Close-Out

## Destination

Every currently-open TODOS.md item (as of 2026-07-22) has either an
implementation-ready ticket or an explicit close/defer decision, so nothing
sits in backlog limbo. A one-time close-out, not a standing backlog-grooming
process — the map is done once these specific open items are dispositioned.

## Notes

- Domain: edgartools-platform, AWS-first SEC EDGAR data platform. Consult
  `CONTEXT.md` (root) and `CLAUDE.md` before introducing new terms or
  contradicting documented conventions.
- Every session should default to `/grilling` + `/domain-modeling` for
  design-tradeoff tickets; use `/research` for fact-finding that requires
  external documentation, third-party API behavior, or live infra state —
  not code already understood in this repo.
- Reviewed TODOS.md in full (2026-07-22): of ~26 entries, all but four are
  already RESOLVED/MITIGATED with evidence. This map covers exactly those
  four (well, three tickets + one already-settled decision noted below).

## Decisions so far

- **financial_derived YoY tiebreaker (Issue 3B)** — not a wayfinder ticket;
  already decided and re-confirmed. TODOS.md's own entry records a
  2026-07-18 re-evaluation ("stays deferred, decision unchanged") against
  the Ticket 20 anti-overclaim doctrine. No new decision needed here;
  revisit only if `filed_date` becomes available in silver/gold for an
  unrelated reason.
- [Does the completed prodb→prod cutover leave runtime_access roles still shared?](issues/01-runtime-access-role-sharing-check.md) — No: the 2026-07-19 cutover permanently namespaced prod's roles apart (`sec_platform_prod_runner_*` vs dev's unnamespaced `sec_platform_runner_*`), confirmed live via ECS task definitions. Separation is accidental (one account root overrides the prefix, the module itself still isn't fixed to namespace by default) but holds today — TODOS.md's re-verify flag can close.
- [CI-runs-dbt-against-live-Snowflake (Issue 2B): invest now or keep deferring?](issues/04-ci-dbt-live-snowflake-investment-decision.md) — Invest now: `dbt run --select state:modified+ --full-refresh` + `dbt test` on PRs touching `infra/snowflake/dbt/**`, using dedicated CI creds scoped to `EDGARTOOLS_DEV_DEPLOYER` (not the existing accountadmin smoke-test secrets). Prerequisite confirmed still outstanding: the `EDGARTOOLS_DEV_DEPLOYER` SELECT grant is still ad-hoc, not codified in Terraform/bootstrap SQL — must land first, plus the analogous unchecked `EDGARTOOLS_PROD_DEPLOYER` grant. Decision only; codifying the grant and wiring the CI job are follow-up implementation work.
- [Seed universe: which IPO-detection source to build?](issues/02-seed-universe-ipo-detection-source.md) — No new detection code: `daily-incremental`'s existing impacted-CIK discovery already marks any brand-new CIK active regardless of form type. The real gap is that nothing schedules `daily-incremental` to run (confirmed via `aws events list-rules`, zero rules target it) — fix is a daily EventBridge schedule, built but **not yet applied to prod** (needs explicit go, same as Ticket 20's launch gate).
- [Seed universe: what signal determines a company is no longer active?](issues/03-seed-universe-active-signal-source.md) — Form 15 deregistration only (not Form 25 — many delisted companies keep filing as OTC stocks), filtered from the same daily-index pipeline. **Implemented and merged**: `_ciks_filing_form15`/`_demote_deregistered_ciks` in `warehouse_orchestrator.py`, plus a fix for a real landmine surfaced along the way (`_apply_submission_snapshot_to_silver` was silently un-demoting any unrecognized `tracking_status` back to `"active"`). Takes effect once daily-incremental actually runs — tracked under ticket 02, not duplicated.

## Not yet specified

(none identified during breadth-first frontier mapping 2026-07-22 — the
four items below are believed to cover the full open surface of TODOS.md
as reviewed)

## Out of scope

(none yet — nothing has been ruled beyond this destination)
