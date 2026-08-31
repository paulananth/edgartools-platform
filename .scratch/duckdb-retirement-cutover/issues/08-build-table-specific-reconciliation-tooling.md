# 08 — Build the Table-Specific Reconciliation Tooling for This Cutover

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

**Status:** done

- [x] **Reconciliation tooling implements all four checks per table.** New
      package `edgar_warehouse/table_reconciliation/`: `contracts.py`
      declares a `TableContract` per table (business keys reused directly
      from `silver_protection.PROTECTED_TABLE_REGISTRY` — the target set is
      every registry table except `pipeline_run_lease`, which is run-level
      bookkeeping, not SEC content, per this ticket's own disjointness
      note); `sql_checks.py` implements the four checks as store-agnostic
      SQL against anything satisfying the repo's existing `.fetch(sql,
      params)` reader protocol (`orphan_count` for both bronze-to-silver
      key expectations and required-parent integrity, since both are the
      same orphan-detection primitive applied to two different declared
      relationships; `duplicate_key_group_count` for PK uniqueness;
      `fetch_key_cohort`/`fetch_rows_by_keys` plus `digest.py`'s SHA-256
      primitives for the semantic-content digest); `collector.py`
      (`reconcile_table`) runs all four per table and emits one
      unambiguous `overall_status`. Required-parent declarations were
      independently derived from the domain model, then cross-checked
      against `validate_data_quality.py`'s existing, already-reviewed
      `_FK_CHECKS` list (18 of the 30 tables) and found to agree on every
      overlapping entry — not imported directly (that list is private to a
      narrower-scoped QA module), re-declared here as this ticket's own
      canonical source, extended to the 12 tables that module doesn't
      cover.
- [x] **`sec_thirteenf_holding` included and completes in bounded time.**
      Confirmed live against real prod data (2026-08-31, `EDGARTOOLS_PROD`):
      bronze-to-silver, required-parent, and PK-uniqueness are single-pass
      SQL aggregates (`COUNT`/`GROUP BY`) — all three completed in well
      under a minute against the table's real ~6.8M DuckDB rows. The
      semantic-content digest is the only per-row-comparison check and is
      cohort-sampled (default 500 keys, boundary + stable-hash-ordered
      fill — never a full scan), per `fetch_key_cohort`'s design.
- [x] **Case selection covers routing-band, volume, boundary, parser,
      no-op** — **and `guarded-publication` is explicitly declared
      non-transferable, not fabricated.** New `case_coverage.py` names
      which table(s) stand as evidence for each category and states
      plainly, in its own module docstring, that `guarded-publication`
      named BatchSilver's shared-object ETag-promotion race — a write-path
      concurrency concern with no analogue in this tool's read-only,
      single-writer-per-store comparison — so it is declared out of scope
      rather than mapped to something that doesn't actually correspond
      (same "an inherited framing doesn't survive contact" pattern this
      map's own Tickets 06/07 already established). `routing_band` and
      `boundary` are satisfied by construction (every table/every cohort,
      respectively) rather than by a single special case; `no_op` is
      **proven, not asserted** — see the dry-run item below.
- [x] **A dry run against today's dual-write state produces a real report
      — with one deliberate, documented deviation from this ticket's own
      literal wording.** Run live against `EDGARTOOLS_PROD` (2026-08-31),
      not simulated: `WAREHOUSE_STORAGE_ROOT` pointed at the real
      `s3://edgartools-prod-warehouse-690839588395` bucket (1.8GB canonical
      `silver.duckdb`, hydrated fresh each run) and `SnowflakeSilverReader`
      connected via the `edgartools-prod` SnowCLI connection.
      **Deviation:** this ticket's own text says "Snowflake landing zone,"
      but the tooling compares DuckDB canonical against
      `EDGARTOOLS_SILVER` (the dbt-collapsed, current-state layer) instead
      of `EDGARTOOLS_SILVER_LANDING` (the raw, append-only, multi-
      `parse_sequence`-per-key ingest buffer) — PK uniqueness and a
      current-state semantic digest are not meaningful concepts against an
      append-only log where the same key legitimately appears at multiple
      parse sequences by design; `EDGARTOOLS_SILVER` is also what
      `SnowflakeSilverReader` (this repo's existing, already-live
      DuckDB/Snowflake dual-target reader abstraction, `silver-snowflake-
      migration` Ticket 12) already targets. Full-universe dry run (all 30
      tables, cohort-size 200) completed in 2m25s including the S3
      hydrate, exit 1 (correctly fail-closed: 7 of 30 tables genuinely
      failed against live data — real orphan/digest findings, e.g.
      `sec_company_filing` 22 cik-orphans, `sec_financial_fact` 67,668
      accession-orphans, several small tables' semantic digests diverging
      under key-intersection scoping — logged here as real signal the tool
      correctly surfaced, **not fixed in this ticket**, which builds the
      tool rather than auditing every finding it produces; a natural
      follow-up ticket). The freshness-skew design (advisor-flagged before
      implementation) was also confirmed live and correct: tables with an
      `authority_column` (e.g. `sec_thirteenf_holding`, `sec_financial_
      fact`) reported large `out_of_scope_count`s (Snowflake's collapse
      lags DuckDB canonical by design, per this map's own well-documented
      `target_lag` notes) with `semantic_content_digest.status="pass"` on
      the in-scope subset, rather than a false FAIL. The `no_op` case was
      independently proven with two genuine, separate live invocations
      (~2 minutes apart, same `--tables`): `no_op_rerun_check.status ==
      "pass"`, `drifted_tables == []` — confirming this tool's own rerun
      idempotency against an unchanged Snowflake watermark, exactly as
      `case_coverage.py`'s `no_op_note` promises. Live report JSON was not
      committed (ephemeral snapshot of real production data, not a
      fixture) — reproduce with
      `edgar-warehouse table-reconcile [--tables ...] [--compare-to
      <prior report.json>]` against a real environment.
- [x] **The fail-closed assertion output is unambiguous PASS/FAIL per
      table, not prose.** `report.py`'s `build_report` emits a literal
      `overall_status: "pass"|"fail"` on every table and on the report as
      a whole, plus a `tables_failing` list; the CLI handler
      (`table_reconciliation/cli.py`) translates that directly to exit
      code 0/1 — no human interpretation step. `--compare-to` adds the
      no-op check as its own `no_op_rerun_check.status` field, same
      contract.

**Not fixed here (deliberately out of scope):** the 7 real findings the
live dry run surfaced against current production data (see above) are
genuine candidates for follow-up investigation, not defects in this
ticket's own deliverable — this ticket's job was proving the tool works,
which the dry run did unambiguously.

**Three-axis review (Standards/Spec/GoF, CLAUDE.md hard rule)** ran before
committing, as three separate parallel `general-purpose` agents against the
staged diff. Outcomes:

- **GoF**: healthy, zero findings. Reviewed `_TABLE_RELATIONSHIPS`'s dict
  shape (plain declarative data, no per-entry branching — not a disguised
  type hierarchy), `_semantic_digest_result`'s one real branch (data-
  intrinsic, not a scattered Strategy/State smell), and the overlap with
  `validate_data_quality.py`'s `_FK_CHECKS`/`_orphan_count` (`git log
  --follow` shows only 4 low-churn commits on that file, no evidence of
  repeated lockstep change; genuinely different interfaces — single-store
  `db` object vs. the duck-typed `Reader` Protocol spanning both stores).
  No fixes recommended.
- **Standards**: 4 findings, all fixed. (1) Dead code — unused `_COMPANY`/
  `_FILING` link templates in `contracts.py` — removed. (2) No test tied
  `_TABLE_RELATIONSHIPS` back to `_FK_CHECKS`, risking exactly the
  "sibling path silently diverged" shape CLAUDE.md documents repeatedly —
  added `test_bronze_anchor_agrees_with_validate_data_quality_fk_checks`
  (`tests/table_reconciliation/test_contracts.py`), asserting every
  `_FK_CHECKS` entry's parent link matches this module's `bronze_anchor`
  exactly, as a durable regression test of the manual cross-check already
  documented in `contracts.py`'s own docstring. (3) `digest.py`'s
  duplication with two other hash/normalize implementations elsewhere in
  the repo — already self-documented as a deliberate, reasoned deviation
  with the unification opportunity flagged as future work; no further
  action. (4) `table_reconciliation/cli.py`'s docstring cited the wrong
  precedent for its subparser *registration* mechanism (actually mirrors
  `mdm`'s `register_mdm_subparser`, not `gold-verify-live`'s inline
  registration — only the handler-body pattern mirrors `gold-verify-live`)
  — docstring corrected to distinguish the two.
- **Spec**: no missing requirements, no scope creep (the `--stat` diff
  against `origin/main` looked inflated because this branch forked before
  4 unrelated tickets merged to `main`; the real diff, per `git status
  --short`, is exactly this ticket's files). 3 "looks done but
  questionable" notes: (1) the `EDGARTOOLS_SILVER`-vs-landing-zone
  deviation (already documented above) — noted as something that ideally
  should have been raised as a question before implementing rather than
  presented as a completed deviation; accepted as-is, no code change,
  since the technical rationale holds and the deviation is prominently
  documented, not hidden. (2) `collector.py`'s `_semantic_digest_result`
  built two SQL fragments with double-quoted identifiers and skipped
  `sql_checks.safe_identifier()`, contradicting `sql_checks.py`'s own
  documented unquoted-identifier convention (harmless today — both call
  sites only ever run against `duckdb_reader`, never Snowflake — but a
  latent trap for reuse) — fixed: both sites now use
  `sql_checks.safe_identifier()` and unquoted identifiers, consistent with
  every other call in the module. (3) `case_coverage.py`'s five non-
  `volume_large` categories have thin direct test coverage — a genuine gap,
  not a spec-compliance failure; not fixed in this pass (out of scope for
  a review-driven fix; case coverage itself is proven via the live dry run
  documented above, not solely via unit assertions).

Full targeted suite (`tests/table_reconciliation/` +
`tests/unit/test_runtime_imports.py`) re-run after applying all fixes: 56
passed. `mypy edgar_warehouse/table_reconciliation/`: clean, 8 source
files, no issues.
