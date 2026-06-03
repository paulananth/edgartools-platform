# Phase 5: Source To MDM Load Path - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-02 (update session; original assumptions-mode log was 2026-05-16)
**Phase:** 05-source-to-mdm-load-path
**Areas discussed:** Live AWS validation scope, Entity coverage (new work), Phase 5 → Phase 6 handoff, Stale tracking close-out, SQLite/Snowflake MDM target, Securities from XBRL

---

## Context at Session Start

Plans 05-01 through 05-04 had been executed (all 28 tests passing) but VALIDATION.md was never signed off, ROADMAP.md showed 05-03/04 unchecked, and global STATE.md showed Phase 5 at 0%. User confirmed wanting to update context and replan (add plan 05-05).

---

## Live AWS Validation Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Local tests are sufficient | 28/28 pass with real DuckDB fixtures | |
| Live S3 run required | Bounded parse-ownership-bronze run against real S3 bronze | ✓ |
| Document the gap, close anyway | Note missing live run, accept the risk | |

**User's choice:** Live S3 run required — local tests alone are not sufficient to close Phase 5.

| Option | Description | Selected |
|--------|-------------|----------|
| Any active CIK from tracked universe | Opportunistic first CIK | |
| Specific CIK I'll provide | User provides known CIK | |
| You decide | Researcher picks based on available S3 bronze | ✓ |

| Option | Description | Selected |
|--------|-------------|----------|
| Nonzero ownership rows written to silver | At least 1 sec_ownership_reporting_owner row | |
| Full silver-to-MDM round trip | parse-ownership-bronze writes, mdm run loads person entity | ✓ |
| Parse metrics + row count log | parse_ownership_bronze_completed metrics >0 | |

| Option | Description | Selected |
|--------|-------------|----------|
| 5th plan in Phase 5 (05-05-PLAN.md) | Keeps it inside Phase 5 | ✓ |
| Separate verify-work task | Lighter weight, no full plan | |
| Inline in the CONTEXT.md update | Just add a prerequisite gate note | |

| Option | Description | Selected |
|--------|-------------|----------|
| Write silver + load MDM (full E2E) | parse-ownership-bronze writes, mdm run loads entities | ✓ |
| Report-only first, then optional write | --dry-run first | |
| Write only the delta | Standard idempotent behavior | |

---

## Entity Coverage (New Work)

**User's free-text prompt:** "is all master data from source is being captured in mdm" — entity coverage question.

| Option | Description | Selected |
|--------|-------------|----------|
| Companies | sec_company rows without MDM entity | ✓ |
| Persons | Non-corporate sec_ownership_reporting_owner without MDM person | ✓ |
| Securities | Ownership transaction rows without MDM security | ✓ |
| Not sure — need an audit | Coverage diff across all 5 domains | ✓ |

| Option | Description | Selected |
|--------|-------------|----------|
| CLI report: silver count vs MDM count per domain | mdm coverage-report subcommand | ✓ |
| Test assertions | pytest checks | |
| Both | Tests gate CI + operator report | |

| Option | Description | Selected |
|--------|-------------|----------|
| New subcommand: mdm coverage-report | Clean separation | ✓ |
| Flag on mdm run: --coverage | Mixes run + report concerns | |
| Standalone script in scripts/ops/ | Like check-neo4j-e2e.py | |

| Option | Description | Selected |
|--------|-------------|----------|
| Count delta only | silver_count, mdm_count, gap per domain | |
| Count + exclusion reason | Also explains why rows are missing | ✓ |
| Sample missing rows | Show first N missing CIKs | |

| Option | Description | Selected |
|--------|-------------|----------|
| Gate: Phase 5 not done until 0 gap | Zero-gap requirement | ✓ |
| Gate with tolerance | Some exclusions expected | |
| Informational only | Phase 6 can proceed regardless | |

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 5 fixes the loader too | Investigate + fix + re-run — all in 05-05 | ✓ |
| Report only in Phase 5, fix in Phase 6 | | |
| Depends on cause | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Only active (tracking_status = 'active') | MDM represents current tracking universe | ✓ |
| All sec_company rows | Every company ever silver | |
| Active + companies mentioned in filings | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Corporate owners excluded, all natural persons included | is_company = true excluded | ✓ |
| All reporting owners included | | |
| Not sure | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Ownership transaction rows only | sec_ownership_non_derivative_txn + derivative | |
| sec_financial_fact / XBRL | Securities from financial statement data | |
| Both ownership transactions AND financial facts | MDM security pool from all sources | ✓ |

| Option | Description | Selected |
|--------|-------------|----------|
| All private funds in silver — zero exclusions | Every sec_private_fund row | ✓ |
| Only funds linked to active tracked advisers | | |
| Let audit reveal behavior | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Ad-hoc operator tool only | Too environment-dependent for CI | |
| CI-friendly with fixtures | Coverage logic tested against real DuckDB fixture | ✓ |
| Both | | |

| Option | Description | Selected |
|--------|-------------|----------|
| 05-06 separate plan | | |
| Fold into 05-05 alongside the live run | Same plan: live S3 E2E + coverage-report + fix gaps | ✓ |
| Two plans: 05-06 report + 05-07 fix | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Assert zero gap against complete fixture | 1 of each entity type in both silver AND MDM | ✓ |
| Assert schema only | Verify output has correct columns | |
| Assert gap detection | Intentional gap in fixture | |

---

## Phase 5 → Phase 6 Handoff

| Option | Description | Selected |
|--------|-------------|----------|
| Non-zero rows in all 5 MDM entity tables + 0-gap coverage-report | | |
| Specific ownership round-trip | | |
| Full 5-domain round-trip against real S3 bronze | | ✓ |

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 6 planning starts after live round-trip (no PR needed) | | |
| Merge Phase 5 to main first, then plan Phase 6 | | ✓ |
| You decide | | |

**User's choice for relationship priority:** "all types" — all relationship types must work, no ordering.

| Option | Description | Selected |
|--------|-------------|----------|
| Entity presence only | Phase 5 proves MDM has all 5 entity types | |
| Relationship-ready check | At least 1 ownership reporting owner linked to company | |
| Full relationship derivation smoke test | Run mdm derive-relationships as part of Phase 5's live validation | ✓ |

| Option | Description | Selected |
|--------|-------------|----------|
| Smoke test only in Phase 5, full coverage in Phase 6 | | |
| Phase 5 absorbs Phase 6 entirely | | |
| Phase 5 expands but stays focused on 1 CIK | Deep single-CIK proof; Phase 6 scales | ✓ |

| Option | Description | Selected |
|--------|-------------|----------|
| A company with Forms 3/4/5 + ADV filings | Exercises all entity types and relationship types | ✓ |
| Two separate CIKs | One ownership-heavy, one ADV-heavy | |
| Researcher picks based on S3 bronze | | |

**Neo4j sync target (free-text):** "use snowflake neo4j hosted graph analytics"
**Clarification:** "mdm sync-graph targets the Snowflake-hosted graph, not standalone Neo4j"
**Codebase check confirmed:** `mdm sync-graph` already uses `SnowflakeGraphSyncExecutor` from `edgar_warehouse/mdm/snowflake_graph.py` — writes to Snowflake `NEO4J_GRAPH_MIGRATION` schema, NOT bolt://.

| Option | Description | Selected |
|--------|-------------|----------|
| They're parallel — neo4j-pipe handles MDM→Snowflake export; neo4j-snowflake handles Native App | | ✓ |
| neo4j-pipe's 05-05 must wait for neo4j-snowflake Phase 3 | | |
| neo4j-pipe's 05-05 can run independently | | |

| Option | Description | Selected |
|--------|-------------|----------|
| graph_nodes_materialized > 0 AND graph_edges_materialized > 0 | | |
| All 11 GRAPH_EDGE_* tables have at least 1 row | | ✓ |
| Non-zero nodes + at least 1 IS_INSIDER edge | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Must already be in S3 — D-09/D-10 hold | No SEC calls in Phase 5 | ✓ |
| 05-05 can trigger targeted SEC fetch | | |
| Researcher selects CIK with existing bronze | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 6 rewritten to absorb Phase 7; Phase 7 deleted | | ✓ |
| Keep Phase 6 and Phase 7 but mark 7 absorbed | | |
| Leave ROADMAP.md as-is | | |

**New Phase 6 name:** "Full Graph Coverage And Verification"

| Option | Description | Selected |
|--------|-------------|----------|
| All active tracked CIKs (full tracking universe) | | ✓ |
| A defined sample (50 CIKs) | | |
| Whatever is currently in S3 | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Zero delta — second run adds exactly 0 new rows | Strict idempotency | ✓ |
| Zero active duplicates | Soft idempotency | |
| You decide | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Snowflake graph table row counts per entity + edge type | | ✓ |
| Pending MDM rows not yet synced | | |
| Both counts + pending rows + missing-edge diagnostics | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Bounded sync required (GRAPH-02 stays) | mdm sync-graph --type IS_INSIDER --limit 100 | ✓ |
| Always sync everything | | |
| Bounded sync is a stretch goal | | |

| Option | Description | Selected |
|--------|-------------|----------|
| All 11 GRAPH_EDGE types in snowflake_graph.py must be populated | | ✓ |
| Only REL-01–REL-04 | Original REQUIREMENTS.md scope | |
| REL-01–REL-04 required; rest are stretch goals | | |

---

## Stale Tracking Close-out

| Option | Description | Selected |
|--------|-------------|----------|
| Part of 05-05 plan | After live validation passes, 05-05 updates all tracking docs | ✓ |
| Separate plan 05-06 | | |
| Manual | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 6 rewritten (Phase 7 scope absorbed); Phase 7 entry removed | | ✓ |
| Phase 6 rewritten; Phase 7 kept but marked absorbed | | |
| Leave Phase 6 and Phase 7 as placeholders | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — add PIPE-04 (coverage-report), PIPE-05 (E2E live round-trip) | | ✓ |
| No — implementation details of existing requirements | | |
| Update PIPE-02/PIPE-03 scope; don't add new IDs | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — update global STATE.md to show Phase 5 at 100% | | ✓ |
| No — global STATE.md updated manually | | |
| Update workstream STATE.md only | | |

| Option | Description | Selected |
|--------|-------------|----------|
| PR merge first, then plan Phase 6 | Consistent with earlier handoff decision | ✓ |
| Plan Phase 6 in parallel with Phase 5 PR review | | |
| Depends on PR review length | | |

| Option | Description | Selected |
|--------|-------------|----------|
| All 28 tests pass + live E2E run logged + coverage-report 0 gap | Three-condition sign-off | ✓ |
| Automated tests pass only | | |
| Live E2E is the only gate | | |

---

## SQLite/Snowflake Compatibility (Additional Area)

| Option | Description | Selected |
|--------|-------------|----------|
| Local SQLite — same database mdm run wrote to | mdm sync-graph must support SQLite | |
| MDM Postgres (separate from local SQLite) | Local Postgres instance | |
| Reconsider: use local Postgres via Docker | More production-realistic | ✓ |

**Notes:** User is on macOS. Per CLAUDE.md: use Colima as Docker daemon. Decision: `colima start` + `docker run --platform linux/amd64 postgres:15`.

| Option | Description | Selected |
|--------|-------------|----------|
| Docker postgres:15 container | Clean slate, matches ECS, via Colima | ✓ |
| Existing local Postgres | May have schema conflicts | |
| Researcher determines availability | | |

---

## Securities From XBRL (Additional Area)

**Context:** Current `MDMPipeline.run_securities()` only reads `sec_ownership_non_derivative_txn` + `sec_ownership_derivative_txn`. User said securities come from "both ownership transactions AND financial facts."

| Option | Description | Selected |
|--------|-------------|----------|
| sec_financial_fact table (XBRL companyfacts) | | ✓ |
| sec_financial_derived or sec_earnings_release | | |
| Reconsider — securities only from ownership transactions | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Researcher investigates sec_financial_fact schema and defines the mapping | | ✓ |
| Each unique (cik, form, concept) tuple is a security | | |
| Reconsider scope: defer XBRL securities to Phase 6 | | |

| Option | Description | Selected |
|--------|-------------|----------|
| Coverage-report gates on ownership-sourced securities only; XBRL → Phase 6 | | ✓ |
| Phase 5 gates on ALL securities regardless of source | | |
| Phase 5 includes XBRL securities if mappable; otherwise ships without | | |

---

## Claude's Discretion

- Researcher selects specific test CIK based on S3 bronze availability (Forms 3/4/5 + ADV both required).
- Researcher determines precise MDM entity exclusion predicates (e.g., `is_company` field name in `sec_ownership_reporting_owner`).
- Bounded `--limit` / `--cik-list` / `--accession-list` controls added to live run only if needed for safe bounded validation.

## Deferred Ideas

- XBRL-sourced securities (sec_financial_fact → MDM security entity): Phase 6 scope.
- neo4j-snowflake Native App verification (Snowflake graph analytics reading NEO4J_GRAPH_MIGRATION tables): neo4j-snowflake Phase 3.
- SEC artifact re-fetch or missing-bronze capture repair: deferred unless explicitly requested.
- Full 100-company AWS runtime proof: Phase 6 success criterion.
