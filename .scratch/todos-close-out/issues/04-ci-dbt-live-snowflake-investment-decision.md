# 04 — CI-runs-dbt-against-live-Snowflake (Issue 2B): invest now or keep deferring?

Type: grilling
Status: resolved
Blocked by: (none)

## Question

TODOS.md's Issue 2B entry has sat deferred since 2026-06-12: `dbt compile`
in CI can't catch Snowflake-execution-only errors (e.g. the nested-window
bug that motivated this entry). Decide: invest now, or keep deferring? If
now: what scope/cadence (full `dbt run` on every PR touching
`infra/snowflake/dbt/**`, `--select state:modified+` for changed models
only, or a nightly scheduled run), and confirm the `EDGARTOOLS_DEV_DEPLOYER`
grants gap blocking `--full-refresh` (TODOS.md, separate entry, marked
RESOLVED for dev 2026-06-13) is still actually resolved before committing
to this.

## Answer

**Decision: invest now.**

1. **Scope/cadence:** `dbt run --select state:modified+ --full-refresh` plus
   `dbt test`, triggered on PRs touching `infra/snowflake/dbt/**`. Not a
   full-graph run on every PR (too slow/costly, re-validates unchanged
   models) and not nightly-only (lets a bad model sit broken on `main` for
   up to a day). `state:modified+` scopes the run to changed models plus
   anything downstream of them, which is exactly the class of bug this gap
   exists to catch (Snowflake-execution-only errors in changed SQL, e.g. the
   Issue 1 nested-window bug).

2. **Credentials:** dedicated CI secrets authenticating as the environment's
   own deployer role — `EDGARTOOLS_DEV_DEPLOYER` for the dev PR job,
   `EDGARTOOLS_PROD_DEPLOYER` for the analogous prod path if/when one is
   added — not a reuse of `smoke-test.yml`'s existing accountadmin secrets.
   Running CI as the real deploy-time role means CI also exercises the real
   deploy-time privilege path, including the grants-gap class of failure
   below; accountadmin would mask that entirely.

3. **Prerequisite confirmed NOT yet done:** verified live against
   `infra/terraform/snowflake/` and `infra/snowflake/sql/bootstrap/` — the
   `EDGARTOOLS_DEV_DEPLOYER` `SELECT` grant on `EDGARTOOLS_SOURCE` is still
   only the 2026-06-13 ad-hoc `GRANT` run by hand as ACCOUNTADMIN (TODOS.md).
   No `GRANT SELECT ... EDGARTOOLS_SOURCE ... TO ROLE EDGARTOOLS_DEV_DEPLOYER`
   exists in Terraform or `01_source_stage.sql`; it would not survive an
   environment rebuild. This must be codified (current + `FUTURE TABLES`
   grant, per the SQL already drafted in TODOS.md) **before** wiring the CI
   job, or `--full-refresh` fails there exactly as it did manually. The
   analogous `EDGARTOOLS_PROD_DEPLOYER` grant (TODOS.md flags as "likely
   needed, not checked") should be verified/added at the same time for
   parity, even though the CI job itself only targets dev.

**Not done in this ticket** (wayfinder plans, doesn't build): codifying the
grant and wiring the GitHub Actions job are implementation work, tracked as
follow-up rather than executed here.
