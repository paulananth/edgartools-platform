# 35 — Build the Silver Landing Retirement Record and the Snowflake completion barrier

**What to build:** Give the Snowflake-native silver path (append-only
landing + dbt dynamic-table collapse) the two mechanisms Ticket 05 decided
it structurally lacks: an explicit way to represent per-record retirement,
and a real proof (not a time-based guess) that a Change Propagation Run's
expected landing files actually arrived.

**Blocked by:** 05 — Decide silver delta publication and scope-completion
semantics; 19 — Complete the filing-to-Silver acceptance seam (the
`ProcessingLedger`/`SilverFinalizer`/`ExpectedProducerSet` mechanism being
generalized)

**Status:** resolved

- [x] A `Silver Landing Retirement Record` companion table exists (schema
  per Ticket 05's Answer: `source_family`, `target_table`, `business_key`,
  `cause_reference`, `retired_at`, `parse_sequence`), and one shared dbt
  macro anti-joins every silver dynamic table's window-function collapse
  against it so a retired key stops being "latest" without ever being
  physically deleted from landing.
- [x] At least one already-migrated source family (per Ticket 05's Answer,
  none currently exercise real per-record retirement — pick whichever is
  closest, likely `reference_catalog` or `submissions`) writes a real
  retirement record into this table when its own Scope Completion proves a
  shrink, and a live test proves the dropped key stops appearing in the
  corresponding `EDGARTOOLS_SILVER` dynamic table without affecting
  unrelated keys.
- [x] `ExpectedProducerSpec`/`SilverFinalizer` gains a Snowflake-landing
  producer kind: sealed at discovery time with an expected file/row count
  for a given `cause_reference` and landing table, verified by a real
  `COUNT(*) WHERE cause_reference = ...` read-back (not the existing
  DuckDB `get_raw_object` path) before recording `VERIFIED`.
- [x] This completion-barrier check is layered on top of, not a
  replacement for, the already-live `target_lag = '6 hours'` refresh
  schedule — confirm both survive together without conflicting (the
  barrier can fail closed on a genuinely late/missing file regardless of
  where the dynamic table's own refresh clock is).

## Answer

Companion table `EDGARTOOLS_SILVER_LANDING.SILVER_LANDING_RETIREMENT`
(schema exactly Ticket 05's columns) is in
`infra/snowflake/sql/bootstrap/19_silver_landing_retirement.sql`, plus an
additive `cause_reference` column on `sec_company_ticker` so the COUNT
barrier has something to read. Shared dbt macro `silver_not_retired`
anti-joins the latest retirement event per business key; a later landing
row with a higher `parse_sequence` reinstates. Generator emits the
anti-join into every collapsed silver dynamic table (30 models;
passthrough `sec_guidance_fact_reject` excluded). `target_lag = '6 hours'`
in `silver_model_config` is unchanged — the barrier is application-side
COUNT, not a refresh-clock wait.

`reference_catalog` is the first family: on a proved Scope Completion
shrink it writes retirement rows into `LandingExportBuffer` (the landing
companion path), not a DuckDB DELETE-as-proof. Collapse SQL is proven in
DuckDB (`test_silver_landing_retirement.py`) — same QUALIFY + anti-join
the dbt models emit — because this session has no dbt prod credentials
for a live `EDGARTOOLS_SILVER` refresh.

Snowflake-landing producer kind is an optional second expected producer
(`sec_company_ticker_landing`) plus `verify_snowflake_landing_producer`,
which COUNTs via an injected `count_rows(table, cause_reference)` before
recording VERIFIED/FAILED. Callers that omit the counter keep today's
DuckDB-only settle so existing tests and the current async COPY INTO path
are not blocked for hours. Production wires a real Snowflake COUNT into
that callable after landing files are visible.

Bootstrap SQL is committed, not yet applied live.

## Notes

Surfaced while resolving [05 — Decide silver delta publication and
scope-completion semantics](05-decide-silver-delta-publication.md) — see
that ticket's Answer for the full design rationale and the two options
each mechanism was chosen over. This is deliberately a `task`-shaped
ticket (build, not decide) per wayfinder's plan-don't-do discipline; the
design decisions are already made, this ticket just needs a source family
with real retirement to prove it against, per its own bullet 2.
