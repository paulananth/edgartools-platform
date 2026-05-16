---
phase: 05
slug: source-to-mdm-load-path
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-16
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
| 05-W0-02 | TBD | 0 | PIPE-02 | T-05-02 | Repeated MDM entity loading keeps domain entity counts stable. | integration | `uv run --extra mdm-runtime --with pytest pytest tests/mdm/test_source_to_mdm_load_path.py::test_entity_load_is_idempotent_for_domain_counts -q` | no - W0 | pending |
| 05-W0-03 | TBD | 0 | PIPE-03 | T-05-03 | Missing silver source exits before MDM session creation or mutation. | unit/CLI | `uv run --extra mdm-runtime --with pytest pytest tests/mdm/test_source_to_mdm_load_path.py::test_missing_silver_source_fails_before_session -q` | no - W0 | pending |
| 05-W0-04 | TBD | 0 | ISO-01, ISO-02 | - | Changed files stay inside the neo4j-pipe scope and avoid loader-fix/generated deployment surfaces. | static review | `git diff --name-only` | manual/static | pending |

---

## Wave 0 Requirements

- [ ] `tests/application/test_parse_ownership_bronze.py` - covers current silver schema, skip already parsed accessions, artifact-registry primary XML reads, missing artifact reporting.
- [ ] `tests/mdm/test_source_to_mdm_load_path.py` - covers local/S3-like `MDM_SILVER_DUCKDB`, missing source before session, table/row preflight, and entity domain count idempotency.
- [ ] Fixture helper to create a tiny real DuckDB file using current silver DDL and synthetic rows for all five entity domains.
- [ ] MDM test setup using existing SQLAlchemy metadata and default seeding patterns.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live S3 bronze primary XML availability | PIPE-01 | Local research did not verify AWS bronze contents or credentials. | Run the bounded operator validation task produced by the plan against the target `WAREHOUSE_BRONZE_ROOT` and `WAREHOUSE_STORAGE_ROOT`; record ownership-form filing, primary artifact, and parsed ownership row counts. |
| Worktree isolation | ISO-01, ISO-02 | Requires review of final changed file set. | Run `git status --short` and `git diff --name-only`; confirm no loader-fix artifacts, generated deployment JSON, gold/dbt, or Step Functions observability files changed. |

---

## Validation Sign-Off

- [ ] All tasks have automated verification or Wave 0 dependencies.
- [ ] Sampling continuity: no 3 consecutive tasks without automated verification.
- [ ] Wave 0 covers all missing references.
- [ ] No watch-mode flags.
- [ ] Feedback latency under 90 seconds for focused tests.
- [ ] `nyquist_compliant: true` set in frontmatter after Wave 0 tests exist and pass.

**Approval:** pending
