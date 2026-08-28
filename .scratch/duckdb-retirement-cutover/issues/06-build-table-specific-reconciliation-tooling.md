# 06 — Build the Table-Specific Reconciliation Tooling for This Cutover

**What to build:** DuckDB Retirement's Ticket 07 (wayfinder decision) chose
this repo's existing Production Release Readiness vocabulary as the cutover
validation standard: digest-based **Table-Specific Reconciliation** per
table (not full diff, not count-only), bounded case-selected reruns
including one real-scale table (not a calendar soak), automated fail-closed
assertion gating a required human approval. This ticket builds the concrete
tooling that implements that standard for this specific migration.

For each table touched by the write-path cutover, prove: bronze-to-silver
key expectations, declared primary-key uniqueness, required-parent
integrity, and a canonical semantic-content digest match between DuckDB
canonical and Snowflake — including explicit legitimate-zero outcomes for
optional and one-to-many parsers (mirroring `Table-Specific Reconciliation`'s
definition in `CONTEXT.md`).

**Must include `sec_thirteenf_holding` (confirmed live at ~6.8M rows) as the
required large-scale case** — Ticket 07's decision explicitly requires at
least one real-scale table in the bounded case selection, and this is the
largest table in the affected set. Round out the case selection with
routing-band, volume, boundary, parser, no-op, and guarded-publication cases,
mirroring the existing `MaxConcurrency4 Data Integrity Evidence` precedent's
case-selection shape (`CONTEXT.md`).

**This ticket is genuinely independent of the cutover itself and can run
today**, against the current dual-write state (DuckDB canonical vs. the
Snowflake landing zone, already live per `silver-snowflake-migration`'s
Ticket 02) as its first proving ground. Confirmed disjoint from
[Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md)'s scope: the
11 bookkeeping tables moving to Snowflake Postgres are all
checkpoint/lease/audit-trail tables, none are SEC content, so this tooling's
target table set doesn't shift underneath it as Ticket 02 lands.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Reconciliation tooling implements all four checks (key expectations,
      PK uniqueness, required-parent integrity, semantic-content digest)
      per table
- [ ] `sec_thirteenf_holding` is included as the large-scale case and the
      tooling completes against it in bounded time (not a full scan every
      run)
- [ ] The case selection covers routing-band, volume, boundary, parser,
      no-op, and guarded-publication scenarios
- [ ] A dry run against today's dual-write state (DuckDB canonical vs.
      Snowflake landing) produces a real report, proving the tooling works
      before the cutover exists to validate
- [ ] The fail-closed assertion output is unambiguous: PASS/FAIL per table,
      not a prose summary a human has to interpret
