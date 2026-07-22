# 04 — CI-runs-dbt-against-live-Snowflake (Issue 2B): invest now or keep deferring?

Type: grilling
Status: open
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

(resolved on close)
