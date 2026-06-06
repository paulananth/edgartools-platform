---
phase: 05
slug: source-to-mdm-load-path
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-16
validated: 2026-06-06
---

# Phase 05 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest, run through `uv` |
| **Config file** | none found |
| **Quick run command** | `uv run --extra mdm-runtime --extra s3 --with pytest pytest tests/mdm/test_source_to_mdm_load_path.py tests/application/test_parse_ownership_bronze.py -q` |
| **Full suite command** | `uv run --extra s3 --extra mdm-runtime --with pytest pytest tests/unit tests/architecture tests/application tests/mdm` |
| **Estimated runtime** | quick: less than 90 seconds; full: project-dependent |

---

## Sampling Rate

- **After every task commit:** Run the quick command for the touched area or the full quick command above.
- **After every plan wave:** Run the quick command plus existing smoke tests touched by the wave.
- **Before `$gsd-verify-work`:** Full suite must be green, or any skipped live AWS/Neo4j checks must be explicitly documented.
- **Max feedback latency:** 90 seconds for focused tests.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-W0-01 | TBD | 0 | PIPE-01 | T-05-01 | Parse existing bronze XML without SEC re-fetch and write current silver ownership tables. | unit/integration | `uv run --extra s3 --with pytest pytest tests/application/test_parse_ownership_bronze.py -q` | no - W0 | pending |
| 05-W0-02 | TBD | 0 | PIPE-01 | T-05-02 | S3-backed `MDM_SILVER_DUCKDB` succeeds through `object_storage.read_bytes()` using real DuckDB bytes and no SEC fetch. | integration | `uv run --extra mdm-runtime --extra s3 --with pytest pytest tests/mdm/test_source_to_mdm_load_path.py::test_s3_backed_silver_source_uses_object_storage_read_bytes -q` | no - W0 | pending |
| 05-W0-03 | TBD | 0 | PIPE-02 | T-05-03 | Repeated MDM entity loading keeps domain entity counts stable. | integration | `uv run --extra mdm-runtime --with pytest pytest tests/mdm/test_source_to_mdm_load_path.py::test_entity_load_is_idempotent_for_domain_counts -q` | no - W0 | pending |
| 05-W0-04 | TBD | 0 | PIPE-03 | T-05-04 | Missing silver source exits before MDM session creation or mutation. | unit/CLI | `uv run --extra mdm-runtime --with pytest pytest tests/mdm/test_source_to_mdm_load_path.py::test_missing_silver_source_fails_before_session -q` | no - W0 | pending |
| 05-W0-05 | TBD | 0 | ISO-01, ISO-02 | - | Changed files stay inside the neo4j-pipe scope and avoid loader-fix/generated deployment surfaces, including untracked files. | static review | `git status --short --untracked-files=all` | manual/static | pending |

---

## Wave 0 Requirements

- [ ] `tests/application/test_parse_ownership_bronze.py` - covers current silver schema, skip already parsed accessions, artifact-registry primary XML reads, missing artifact reporting.
- [ ] `tests/mdm/test_source_to_mdm_load_path.py` - covers local `MDM_SILVER_DUCKDB`, positive `s3://` `MDM_SILVER_DUCKDB` via monkeypatched `object_storage.read_bytes()` returning real DuckDB bytes, missing source before session, table/row preflight, and entity domain count idempotency.
- [ ] Fixture helper to create a tiny real DuckDB file using current silver DDL and synthetic rows for all five entity domains.
- [ ] MDM test setup using existing SQLAlchemy metadata and default seeding patterns.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live S3 bronze primary XML availability | PIPE-01 | Local research did not verify AWS bronze contents or credentials. | Run the bounded operator validation task produced by the plan against the target `WAREHOUSE_BRONZE_ROOT` and `WAREHOUSE_STORAGE_ROOT`; record ownership-form filing, primary artifact, and parsed ownership row counts. |
| Worktree isolation | ISO-01, ISO-02 | Requires review of final changed file set. | Run `git status --short --untracked-files=all`; confirm no loader-fix artifacts, generated deployment JSON, gold/dbt, or Step Functions observability files changed. |

---

## Validation Sign-Off

- [x] All tasks have automated verification or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verification.
- [x] Wave 0 covers all missing references.
- [x] No watch-mode flags.
- [x] Feedback latency under 90 seconds for focused tests.
- [x] `nyquist_compliant: true` set in frontmatter after Wave 0 tests exist and pass.

**Approval:** complete

---

## Live E2E Sign-Off

**Validated:** 2026-06-06

**Scope:** bounded real-data Phase 5 closeout sample. No single available live silver CIK had both
ownership and ADV rows, so the validation used the real ownership sample plus the Phase 10 real ADV
sample that unblocked adviser/fund loading.

| Source | Identifier | Evidence |
|--------|------------|----------|
| Ownership issuer | CIK 712515, accession 0000712515-26-000049 | Form 4 ownership rows loaded from live silver into MDM company/person/security domains |
| ADV adviser/fund | CRD/CIK 105958, accession ADV-105958-20241218 | Vanguard ADV XML from S3 bronze parsed into silver; adviser and private fund loaded |
| Snowflake target | EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION | `mdm sync-graph` materialized Snowflake graph tables via SnowflakeGraphSyncExecutor |

### Automated Verification

| Check | Result |
|-------|--------|
| `pytest tests/mdm/test_source_to_mdm_load_path.py -k coverage_report -q` | 1 passed, 18 deselected |
| `MDM_DATABASE_URL=sqlite:// uv run edgar-warehouse mdm coverage-report --help` | exit 0 |
| `pytest tests/mdm/test_source_to_mdm_load_path.py tests/application/test_parse_ownership_bronze.py -q` | 32 passed, 3 warnings |
| `pytest tests/mdm/test_snowflake_graph_migration.py tests/mdm/test_cli_snowflake_graph.py -q` | 12 passed |

### MDM Counts

| Table | Count |
|-------|-------|
| mdm_company | 1 |
| mdm_person | 1 |
| mdm_security | 1 |
| mdm_adviser | 1 |
| mdm_fund | 1 |
| mdm_entity | 15 |
| mdm_relationship_instance | 4 |

### Coverage Report

| Domain | Silver Count | MDM Count | Gap | Reason |
|--------|--------------|-----------|-----|--------|
| companies | 1 | 1 | 0 | Inactive and dropped companies excluded (`tracking_status != 'active'`) |
| persons | 1 | 1 | 0 | Corporate owners excluded |
| securities | 1 | 1 | 0 | Ownership-sourced only; XBRL-sourced securities deferred to Phase 6 |
| advisers | 1 | 1 | 0 | All ADV filers included |
| funds | 1 | 1 | 0 | All private funds included |

### Snowflake Graph Sync

`edgar-warehouse mdm sync-graph --target-database EDGARTOOLS_DEV --target-schema NEO4J_GRAPH_MIGRATION --mdm-database EDGARTOOLS_DEV --mdm-schema MDM` exited 0.

| Metric | Count |
|--------|-------|
| graph_nodes_synced | 15 |
| graph_edges_synced | 4 |
| missing endpoint rows | 0 |

All 11 relationship-specific `GRAPH_EDGE_*` views exist in
`EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION`.

| Relationship Type | MDM Active | Graph Count | MDM Minus Graph | Notes |
|-------------------|------------|-------------|-----------------|-------|
| AUDITED_BY | 0 | 0 | 0 | Requires fundamentals audit-firm source rows |
| COMPANY_HOLDS | 0 | 0 | 0 | Requires corporate reporting owner |
| EMPLOYED_BY | 0 | 0 | 0 | Requires DEF 14A executive records |
| HAS_PARENT_COMPANY | 0 | 0 | 0 | Unreachable until parent company links are populated |
| HOLDS | 1 | 1 | 0 | Ownership core edge |
| INSTITUTIONAL_HOLDS | 0 | 0 | 0 | Requires 13F holdings |
| ISSUED_BY | 1 | 1 | 0 | Ownership core edge |
| IS_ENTITY_OF | 0 | 0 | 0 | Requires adviser-to-company resolution in source sample |
| IS_INSIDER | 1 | 1 | 0 | Ownership core edge |
| IS_PERSON_OF | 0 | 0 | 0 | Requires adviser-person links in source sample |
| MANAGES_FUND | 1 | 1 | 0 | ADV/private fund edge |

**Phase 5 parity gate:** PASS. `MDM_MINUS_GRAPH = 0` for every active relationship type, and
`IS_INSIDER`, `HOLDS`, and `ISSUED_BY` are nonzero.
