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

## Not yet specified

(none identified during breadth-first frontier mapping 2026-07-22 — the
four items below are believed to cover the full open surface of TODOS.md
as reviewed)

## Out of scope

(none yet — nothing has been ruled beyond this destination)
