# Phase 5: Source To MDM Load Path - Research

**Researched:** 2026-05-16
**Domain:** Existing silver DuckDB to MDM entity load path, plus ownership bronze-to-silver backfill repair
**Confidence:** HIGH for codebase-local implementation surfaces; MEDIUM for live S3/bronze data availability because live AWS data was not queried

<user_constraints>
## User Constraints (from CONTEXT.md)

Source: `.planning/workstreams/neo4j-pipe/phases/05-source-to-mdm-load-path/05-CONTEXT.md` [VERIFIED: codebase grep]

### Locked Decisions

### Bronze-To-Silver Ownership Backfill
- **D-01:** Use the existing edgartools-backed ownership parser path to populate missing Forms 3/4/5 silver tables from bronze primary XML artifacts.
- **D-02:** The repair target is silver ownership data first: `sec_ownership_reporting_owner`, `sec_ownership_non_derivative_txn`, and `sec_ownership_derivative_txn`.
- **D-03:** Do not derive MDM relationships directly from bronze XML. MDM and Neo4j must remain downstream of silver ownership rows.

### Independent Workstream Isolation
- **D-04:** Keep all Phase 5 implementation in the `workspace/neo4j-pipe` worktree and the `neo4j-pipe` planning workstream.
- **D-05:** Do not edit loader-fix artifacts, generated deployment JSON, gold/dbt assets, Step Functions observability work, or unrelated loader code unless required to prove the bronze-to-MDM input contract.

### Existing Command Repair
- **D-06:** Repair and use the existing `parse-ownership-bronze` command rather than adding a second ownership backfill command.
- **D-07:** Fix the current silver schema mismatch in `parse-ownership-bronze`: `sec_company_filing` uses `form` and `report_date`, not `form_type` and `period_of_report`.
- **D-08:** Prefer artifact-registry based reads (`sec_filing_attachment` plus `sec_raw_object`) where possible, because that matches the existing `_run_parse_pipeline` path and works for local fixtures. Path-based bronze lookup remains valid only when registry rows are unavailable and the document path can be derived.

### Bronze Artifact Prerequisite
- **D-09:** Treat already-captured bronze primary XML as the prerequisite for this independent repair. If the XML artifacts are absent, Phase 5 should report the gap clearly and not silently re-fetch SEC data.
- **D-10:** Any SEC fetch or artifact capture repair is outside this Phase 5 default path unless explicitly requested, because the phase goal says existing bronze/silver data and no loader-workstream overlap.

### MDM Source Validation
- **D-11:** Add or tighten MDM preflight validation so `mdm run`, `mdm derive-relationships`, and `mdm load-relationships` fail clearly when required silver source configuration or required ownership tables are missing/empty.
- **D-12:** For company-person Neo4j validation, nonzero `sec_company`, `sec_company_filing`, and `sec_ownership_reporting_owner` rows are required before MDM person and `IS_INSIDER` relationship derivation can be considered testable.

### the agent's Discretion
- Add bounded execution controls only if needed for safe verification, such as `--limit`, `--cik-list`, `--accession-list`, or dry-run/report-only behavior for `parse-ownership-bronze`.
- Keep tests focused on schema compatibility, idempotent re-runs, missing source behavior, and a minimal silver fixture with at least one company, reporting owner, and issuer relationship.

### Deferred Ideas (OUT OF SCOPE)
- SEC artifact re-fetch or missing-bronze capture repair is deferred unless the user explicitly expands Phase 5 beyond existing bronze/silver data.
- Full AWS 100-company runtime proof remains a future requirement after credentials and Neo4j environment are available.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PIPE-01 | Operator can run the MDM entity loaders against an existing local or S3-backed silver DuckDB produced from bronze without re-fetching SEC artifacts. | Use existing `MDM_SILVER_DUCKDB` URI/local reader, validate it before mutation, and repair `parse-ownership-bronze` so ownership rows exist in silver. [VERIFIED: `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md`; `edgar_warehouse/mdm/cli.py:250`; `edgar_warehouse/application/warehouse_orchestrator.py:1237`] |
| PIPE-02 | MDM company, adviser, person, security, and fund loaders are idempotent across repeated runs against the same silver data. | Existing resolvers match or upsert by CIK, CRD, owner CIK/name, issuer/title, and adviser/fund/name; focused tests must assert only domain entity counts stay stable because staging/change-log rows may grow. [VERIFIED: `edgar_warehouse/mdm/resolvers/*.py`; `edgar_warehouse/mdm/survivorship.py:145`] |
| PIPE-03 | Missing silver source configuration fails with a clear operator message that names the required setting and does not partially mutate MDM state. | Current handlers check `MDM_SILVER_DUCKDB`, but they open the MDM session first; planning should move shared silver preflight ahead of `_session()` for `run`, `derive-relationships`, and `load-relationships`. [VERIFIED: `edgar_warehouse/mdm/cli.py:278`; `edgar_warehouse/mdm/cli.py:477`; `edgar_warehouse/mdm/cli.py:499`] |
| ISO-01 | This milestone is developed in `workspace/neo4j-pipe` and does not modify loader-fix artifacts or generated deployment JSON. | The isolated worktree is `/Users/aneenaananth/gsd-workspaces/neo4j-pipe/edgartools-platform`; branch status was clean before research edits. [VERIFIED: `git worktree list`; `git status --short --branch`] |
| ISO-02 | Changes avoid gold refresh, Step Functions failure-observability, and unrelated loader refactors unless required to prove the bronze-to-Neo4j path. | Phase 5 can be limited to `parse-ownership-bronze`, `mdm/cli.py`, `mdm/pipeline.py`, fixtures/tests, and docs; gold/dbt/deployment JSON are not needed. [VERIFIED: `.planning/workstreams/neo4j-pipe/ROADMAP.md`; codebase grep] |
</phase_requirements>

## Project Constraints (from AGENTS.md)

- Keep work AWS-focused; do not add non-AWS deployment, registry, storage, workflow, or secret-management paths. [VERIFIED: `AGENTS.md`]
- Use `uv` for Python dependency management and command execution; do not use bare `pip` for repo workflows. [VERIFIED: `AGENTS.md`]
- Before editing, inspect `git status --short` and `.planning/active-workstream`; the active isolated worktree marker is `neo4j-pipe`. [VERIFIED: `AGENTS.md`; `.planning/active-workstream`]
- Do not overwrite, revert, stage, or commit changes from another runtime; do not edit generated deployment JSON for this phase. [VERIFIED: `AGENTS.md`; `.planning/workstreams/neo4j-pipe/config.json`]
- Preserve loader idempotency; SEC filing artifacts are additive and immutable after capture, and repair paths should require explicit operator intent. [VERIFIED: `AGENTS.md`]
- Do not change the ownership parser import without checking `edgartools` compatibility; the required parser entry remains `from edgar.ownership import Ownership` and `Ownership.from_xml(content)`. [VERIFIED: `AGENTS.md`; `edgar_warehouse/parsers/ownership.py:7`; CITED: `https://edgartools.readthedocs.io/en/stable/parsing-filing-data/`]

## Summary

Phase 5 should not create a parallel loader. Repair the existing `parse-ownership-bronze` path and keep MDM downstream of silver ownership tables. The immediate known defect is a current silver schema mismatch: `parse-ownership-bronze` queries `sec_company_filing.form_type` and orders by `period_of_report`, while the actual silver DDL uses `form` and `report_date`. [VERIFIED: `edgar_warehouse/application/warehouse_orchestrator.py:1256`; `edgar_warehouse/silver_store.py:71`]

MDM source validation needs a shared preflight that runs before an MDM SQLAlchemy session is opened. Current handlers for `mdm run`, `mdm derive-relationships`, and `mdm load-relationships` call `_session()` before `_silver_reader()`, so missing `MDM_SILVER_DUCKDB` can be masked by missing `MDM_DATABASE_URL` and a database session is opened before the source contract is validated. [VERIFIED: `edgar_warehouse/mdm/cli.py:278`; `edgar_warehouse/mdm/cli.py:477`; `edgar_warehouse/mdm/cli.py:499`; `edgar_warehouse/mdm/database.py:73`]

The planner should include a minimal DuckDB fixture that contains all five MDM entity source domains: `sec_company` plus sync/ticker data for companies, `sec_adv_filing`/`sec_adv_office`/`sec_adv_private_fund` for advisers and funds, and `sec_company_filing` plus `sec_ownership_reporting_owner` and `sec_ownership_non_derivative_txn` for people and securities. [VERIFIED: `edgar_warehouse/mdm/pipeline.py:86`; `edgar_warehouse/mdm/pipeline.py:109`; `edgar_warehouse/mdm/pipeline.py:129`; `edgar_warehouse/mdm/pipeline.py:150`; `edgar_warehouse/mdm/pipeline.py:175`]

**Primary recommendation:** Repair `parse-ownership-bronze`, add a shared MDM silver preflight before mutation, update stale current-schema assumptions (`sec_tracked_universe` -> `sec_company_sync_state` or nullable tracking), and prove entity-count stability with a local DuckDB fixture. [VERIFIED: codebase grep]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Silver source configuration validation | API / Backend CLI | Database / Storage | `edgar-warehouse mdm ...` owns operator input and should validate `MDM_SILVER_DUCKDB` before opening MDM state. [VERIFIED: `edgar_warehouse/mdm/cli.py:250`] |
| S3-backed silver localization | API / Backend CLI | Database / Storage | `_silver_reader()` already downloads URI-backed DuckDB through `object_storage.read_bytes()` into a local file before read-only DuckDB connect. [VERIFIED: `edgar_warehouse/mdm/cli.py:250`; `edgar_warehouse/infrastructure/object_storage.py:195`] |
| Ownership XML parse into silver | API / Backend warehouse command | Database / Storage | `parse-ownership-bronze` is a warehouse command that reads bronze artifacts and mutates silver tables, not MDM relational tables. [VERIFIED: `edgar_warehouse/cli.py:335`; `edgar_warehouse/application/warehouse_orchestrator.py:1237`] |
| Entity identity resolution | API / Backend MDM pipeline | MDM SQL database | Resolver classes own idempotent match/create/upsert behavior for companies, advisers, persons, securities, and funds. [VERIFIED: `edgar_warehouse/mdm/resolvers/*.py`] |
| Relationship derivation | API / Backend MDM pipeline | MDM SQL database | Phase 5 needs source readiness only; full relationship coverage is Phase 6. [VERIFIED: `.planning/workstreams/neo4j-pipe/ROADMAP.md`] |
| Workstream isolation | Repository / Planning | Git worktree | Implementation belongs in `workspace/neo4j-pipe`; loader-fix artifacts and generated deployment JSON are protected. [VERIFIED: `.planning/workstreams/neo4j-pipe/config.json`] |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `edgartools` | 5.30.0 | Parse Forms 3/4/5 ownership XML through `edgar.ownership.Ownership.from_xml`. | Existing dependency and official docs identify Forms 3/4/5 as `Ownership` data objects parsed from XML. [VERIFIED: `uv run --extra mdm-runtime --extra s3 python ...`; CITED: `https://edgartools.readthedocs.io/en/stable/parsing-filing-data/`] |
| `duckdb` | 1.5.2 | Read silver DuckDB fixtures and production silver files. | Existing silver store and MDM reader use DuckDB; official Python API supports `duckdb.connect(database, read_only=True)`. [VERIFIED: `uv run --extra mdm-runtime --extra s3 python ...`; CITED: `https://duckdb.org/docs/current/clients/python/reference/`] |
| `SQLAlchemy` | 2.0.49 | MDM relational session/model layer. | Existing MDM database models, migrations, and resolvers are SQLAlchemy-based. [VERIFIED: `edgar_warehouse/mdm/database.py`; `uv run --extra mdm-runtime --extra s3 python ...`] |
| `fsspec` / `s3fs` | 2026.3.0 / 2026.3.0 | Read and write S3-backed objects through existing object storage adapter. | Existing `StorageLocation` and `read_bytes()` use `fsspec.filesystem(protocol)` for remote roots. [VERIFIED: `edgar_warehouse/infrastructure/object_storage.py:158`; `edgar_warehouse/infrastructure/object_storage.py:195`] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `psycopg2-binary` | 2.9.12 | PostgreSQL driver for live MDM runtime. | Needed when running against AWS MDM PostgreSQL through `MDM_DATABASE_URL`; local tests can use SQLite. [VERIFIED: `pyproject.toml`; `edgar_warehouse/mdm/database.py:73`] |
| `boto3` | 1.42.91 | AWS helper for older `seed-from-silver` S3 download path. | Prefer existing `object_storage.read_bytes()` for new preflight/localization work; only use boto3 where existing code already does. [VERIFIED: `edgar_warehouse/mdm/cli.py:331`; `pyproject.toml`] |
| `neo4j` | 6.1.0 | Graph sync client. | Not required for Phase 5 entity loading; keep graph sync disabled or credentials unset in Phase 5 tests. [VERIFIED: `edgar_warehouse/mdm/cli.py:42`; `.planning/workstreams/neo4j-pipe/ROADMAP.md`] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Existing `parse-ownership-bronze` | New ownership backfill command | Rejected by locked decision D-06; duplicate command would split operator behavior and test coverage. [VERIFIED: `05-CONTEXT.md`] |
| `edgartools` parser adapter | Custom XML parser | Rejected by D-01 and AGENTS.md; custom parsing would duplicate Form 3/4/5 edge cases. [VERIFIED: `05-CONTEXT.md`; `AGENTS.md`] |
| Existing `object_storage.read_bytes()` | Direct boto3 download everywhere | Direct boto3 would bypass existing URI/protocol handling and duplicate local/S3 behavior. [VERIFIED: `edgar_warehouse/infrastructure/object_storage.py:195`] |

**Installation:**

```bash
uv sync --extra s3 --extra mdm-runtime
```

No new permanent project package is required for Phase 5. [VERIFIED: `pyproject.toml`; `uv run --extra mdm-runtime --extra s3 python ...`]

**Version verification:**

```bash
uv run --extra mdm-runtime --extra s3 python -c "import importlib.metadata as m; pkgs=['edgartools','duckdb','fsspec','s3fs','sqlalchemy','psycopg2-binary','neo4j','boto3','pydantic']; [print(p, m.version(p)) for p in pkgs]"
```

The command verified `edgartools 5.30.0`, `duckdb 1.5.2`, `fsspec 2026.3.0`, `s3fs 2026.3.0`, `sqlalchemy 2.0.49`, `psycopg2-binary 2.9.12`, `neo4j 6.1.0`, `boto3 1.42.91`, and `pydantic 2.13.3`. [VERIFIED: local command]

## Package Legitimacy Audit

No new external project dependency is recommended for this phase, so the Package Legitimacy Gate is not required. [VERIFIED: `pyproject.toml`; phase scope]

If the local environment lacks `pytest`, validation can use a transient `uv run --with pytest ...` command rather than adding a dependency in this phase. [VERIFIED: local command; tests import `pytest`]

## Architecture Patterns

### System Architecture Diagram

```text
Operator command
  |
  v
edgar-warehouse parse-ownership-bronze
  |
  +--> open silver DuckDB
  |      |
  |      +--> select Forms 3/4/5 from sec_company_filing.form
  |      +--> skip accessions already in sec_ownership_reporting_owner
  |      +--> read primary XML through sec_filing_attachment -> sec_raw_object
  |      +--> fallback to bronze path only if registry rows are unavailable
  |      +--> parse with edgartools Ownership.from_xml
  |      +--> merge ownership rows into silver
  |
  v
edgar-warehouse mdm run/load-relationships
  |
  +--> shared silver source preflight before _session()
  |      |
  |      +--> MDM_SILVER_DUCKDB present
  |      +--> local path exists or URI can be downloaded through object_storage
  |      +--> DuckDB opens read-only
  |      +--> required tables exist and required row counts are nonzero
  |
  v
MDMPipeline resolvers
  |
  +--> companies from sec_company (+ sync/ticker data if available)
  +--> advisers from sec_adv_filing/sec_adv_office
  +--> persons from sec_ownership_reporting_owner joined to sec_company_filing
  +--> securities from sec_ownership_non_derivative_txn joined to sec_company_filing
  +--> funds from sec_adv_private_fund
  |
  v
MDM SQL tables
```

### Recommended Project Structure

```text
edgar_warehouse/
  application/warehouse_orchestrator.py      # repair parse-ownership-bronze source query and artifact read path
  mdm/cli.py                                # shared MDM_SILVER_DUCKDB preflight before DB session/mutation
  mdm/pipeline.py                           # fix current silver tracking lookup and keep entity loaders idempotent
tests/
  application/test_parse_ownership_bronze.py # schema/artifact-registry regression tests
  mdm/test_source_to_mdm_load_path.py        # DuckDB fixture, missing source, idempotency tests
```

This structure keeps changes in existing command/pipeline ownership boundaries. [VERIFIED: codebase grep]

### Pattern 1: Shared Silver Preflight Before Mutation

**What:** Resolve and validate `MDM_SILVER_DUCKDB` before calling `_session()` or constructing `MDMPipeline`. [VERIFIED: `edgar_warehouse/mdm/cli.py:278`]

**When to use:** Use for `mdm run`, `mdm derive-relationships`, and `mdm load-relationships`, because all three read silver and can mutate MDM. [VERIFIED: `edgar_warehouse/mdm/cli.py:278`; `edgar_warehouse/mdm/cli.py:477`; `edgar_warehouse/mdm/cli.py:499`]

**Example:**

```python
# Source pattern: edgar_warehouse/mdm/cli.py and DuckDB Python API docs
def _require_silver_reader(required_tables: dict[str, bool]):
    try:
        reader = _silver_reader()
    except Exception as exc:
        print(f"Cannot open MDM_SILVER_DUCKDB: {exc}", file=sys.stderr)
        return None, 1
    if reader is None:
        print("MDM_SILVER_DUCKDB is required for this command.", file=sys.stderr)
        return None, 1
    missing_or_empty = _validate_silver_tables(reader, required_tables)
    if missing_or_empty:
        print("Silver DuckDB is not ready: " + "; ".join(missing_or_empty), file=sys.stderr)
        return None, 1
    return reader, 0
```

### Pattern 2: Artifact-Registry Primary XML Read

**What:** Prefer `sec_filing_attachment` rows marked `is_primary` and `sec_raw_object.storage_path` over manual prefix listing. [VERIFIED: `edgar_warehouse/application/warehouse_orchestrator.py:2079`; `edgar_warehouse/silver_store.py:267`; `edgar_warehouse/silver_store.py:285`]

**When to use:** Use when repairing `parse-ownership-bronze`, because registry rows work with local fixtures and S3-backed storage through the same `read_bytes()` adapter. [VERIFIED: `05-CONTEXT.md`; `edgar_warehouse/infrastructure/object_storage.py:195`]

**Example:**

```python
# Source pattern: edgar_warehouse/application/warehouse_orchestrator.py:_read_primary_artifact_bytes
payload = _read_primary_artifact_bytes(db, accession_number)
content = payload.decode("utf-8", errors="replace")
parsed = parse_ownership(accession_number, content, form_type)
```

### Pattern 3: Current Silver Schema Querying

**What:** Query current table/column names from `silver_store.py` DDL rather than stale comments. [VERIFIED: `edgar_warehouse/silver_store.py`]

**When to use:** Use for all Phase 5 source queries. `sec_company_filing` has `form` and `report_date`; current sync state is `sec_company_sync_state`, while `sec_tracked_universe` appears only in stale references and is not created by the DDL. [VERIFIED: `edgar_warehouse/silver_store.py:71`; `edgar_warehouse/silver_store.py:351`; `rg sec_tracked_universe`]

**Example:**

```sql
-- Source: edgar_warehouse/silver_store.py current DDL
SELECT f.accession_number, f.cik, f.form
FROM sec_company_filing f
WHERE f.form IN ('3','3/A','4','4/A','5','5/A')
ORDER BY f.cik, f.report_date
```

### Anti-Patterns to Avoid

- **Opening MDM before source validation:** This can mask `MDM_SILVER_DUCKDB` errors behind `MDM_DATABASE_URL` errors and weakens the no-mutation guarantee. [VERIFIED: `edgar_warehouse/mdm/cli.py:278`; `edgar_warehouse/mdm/database.py:73`]
- **Treating zero ownership rows as success:** The milestone audit found silver candidates with hundreds of thousands of ownership-form filings and zero reporting owners; this is a blocked source contract, not a harmless no-op. [VERIFIED: `.planning/workstreams/neo4j-pipe/v1.1-MILESTONE-AUDIT.md`]
- **Using `sec_tracked_universe` in new MDM load tests:** The current silver DDL does not create that table; use `sec_company_sync_state` or tolerate missing tracking metadata. [VERIFIED: `edgar_warehouse/silver_store.py:351`; `rg sec_tracked_universe`]
- **Fetching SEC artifacts in Phase 5 tests:** The phase is explicitly about existing bronze/silver data and no re-fetching. [VERIFIED: `05-CONTEXT.md`; `.planning/workstreams/neo4j-pipe/ROADMAP.md`]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Forms 3/4/5 XML parsing | Custom XML parser | Existing `edgar_warehouse.parsers.ownership.parse_ownership()` backed by `edgartools` | Official docs and AGENTS.md identify `Ownership.from_xml` as the parser path, and repo adapter already shapes rows for silver. [VERIFIED: `edgar_warehouse/parsers/ownership.py`; CITED: `https://edgartools.readthedocs.io/en/stable/parsing-filing-data/`] |
| S3/local object reads | Direct boto3 or ad hoc `open()` branching | `edgar_warehouse.infrastructure.object_storage.read_bytes()` | Existing adapter handles local paths and approved remote protocols consistently. [VERIFIED: `edgar_warehouse/infrastructure/object_storage.py:195`] |
| Entity matching/idempotency | New dedupe logic in CLI handlers | Existing MDM resolver classes | Resolvers already own match/create/upsert decisions for all five domains. [VERIFIED: `edgar_warehouse/mdm/resolvers/*.py`] |
| Schema creation for MDM tests | Hand-built partial table SQL | SQLAlchemy `Base.metadata.create_all()` plus `seed_defaults()` or existing fixtures | Existing tests already use SQLAlchemy metadata for in-memory MDM tests. [VERIFIED: `tests/mdm/conftest.py:101`; `edgar_warehouse/mdm/migrations/runtime.py:380`] |
| DuckDB query execution | CSV/parquet fixture parsing | Real DuckDB fixture file | MDM reader protocol executes SQL against DuckDB and should be tested against the same interface. [VERIFIED: `edgar_warehouse/mdm/resolvers/base.py:19`; `edgar_warehouse/mdm/cli.py:250`] |

**Key insight:** The risky work is contract repair at subsystem boundaries, not parsing or dedupe algorithms. Reuse existing parser, object storage, DuckDB, and resolver layers so Phase 5 only proves the silver-to-MDM contract. [VERIFIED: codebase grep]

## Common Pitfalls

### Pitfall 1: Repairing the Wrong Silver Schema

**What goes wrong:** `parse-ownership-bronze` continues to query `form_type` and `period_of_report`, so it fails or selects zero current rows. [VERIFIED: `edgar_warehouse/application/warehouse_orchestrator.py:1256`; `edgar_warehouse/silver_store.py:71`]

**Why it happens:** Some comments and older scripts still reference previous table names or workflow assumptions. [VERIFIED: `rg sec_tracked_universe`; `infra/scripts/run-mdm-pipeline.sh`]

**How to avoid:** Anchor all SQL to `silver_store.py` DDL and add regression tests that fail on old columns. [VERIFIED: `edgar_warehouse/silver_store.py`]

**Warning signs:** DuckDB binder errors for missing columns or zero selected ownership-form filings despite nonzero `sec_company_filing` rows. [VERIFIED: `.planning/workstreams/neo4j-pipe/v1.1-MILESTONE-AUDIT.md`]

### Pitfall 2: Conflating Missing Bronze XML With Missing Parsed Silver Rows

**What goes wrong:** An operator sees zero `sec_ownership_reporting_owner` rows and cannot tell whether bronze primary XML is missing or the parser path is broken. [VERIFIED: `.planning/workstreams/neo4j-pipe/v1.1-MILESTONE-AUDIT.md`; `scripts/ops/check-neo4j-e2e.py:96`]

**Why it happens:** Current readiness checks count silver output tables but do not always report artifact-registry availability and parse-run status together. [VERIFIED: `scripts/ops/check-neo4j-e2e.py:96`; `scripts/ops/verify-counts.py:106`]

**How to avoid:** Preflight/report three distinct counts: ownership-form filings, primary artifacts (`sec_filing_attachment` joined to `sec_raw_object`), and parsed ownership rows. [VERIFIED: `scripts/ops/check-neo4j-e2e.py:96`]

**Warning signs:** Nonzero Forms 3/4/5 filings with zero `sec_raw_object`/`sec_filing_attachment` indicates missing bronze artifacts; nonzero artifacts with zero ownership rows indicates parse/backfill failure. [VERIFIED: `scripts/ops/check-neo4j-e2e.py:277`]

### Pitfall 3: Validating After Mutation Setup

**What goes wrong:** Missing silver configuration exits through a different missing-environment error or opens a database session before the source is validated. [VERIFIED: `edgar_warehouse/mdm/cli.py:278`; `edgar_warehouse/mdm/database.py:73`]

**Why it happens:** `_handle_run`, `_handle_derive_relationships`, and `_handle_load_relationships` call `_session()` before `_silver_reader()`. [VERIFIED: `edgar_warehouse/mdm/cli.py:278`; `edgar_warehouse/mdm/cli.py:477`; `edgar_warehouse/mdm/cli.py:499`]

**How to avoid:** Refactor to a single preflight helper that returns a reader or exit code before `_session()`. [VERIFIED: local code analysis]

**Warning signs:** A test with `MDM_SILVER_DUCKDB` unset and `MDM_DATABASE_URL` unset raises `KeyError: MDM_DATABASE_URL` instead of naming `MDM_SILVER_DUCKDB`. [VERIFIED: `edgar_warehouse/mdm/database.py:73`]

### Pitfall 4: Over-Asserting Idempotency

**What goes wrong:** Tests fail because `mdm_entity_attribute_stage` or `mdm_change_log` grows across repeated runs even while domain entity counts remain stable. [VERIFIED: `edgar_warehouse/mdm/survivorship.py:145`; `edgar_warehouse/mdm/resolvers/base.py:108`]

**Why it happens:** Resolver runs intentionally stage source attributes and log changes each pass; requirement PIPE-02 is about company, adviser, person, security, and fund counts. [VERIFIED: `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md`]

**How to avoid:** Assert stable counts for `mdm_company`, `mdm_adviser`, `mdm_person`, `mdm_security`, and `mdm_fund`; do not assert all MDM tables are unchanged. [VERIFIED: `edgar_warehouse/mdm/database.py:167`; `edgar_warehouse/mdm/database.py:193`; `edgar_warehouse/mdm/database.py:223`; `edgar_warehouse/mdm/database.py:247`; `edgar_warehouse/mdm/database.py:272`]

**Warning signs:** First and second run produce equal domain entity counts but extra staging/change-log rows. [VERIFIED: `edgar_warehouse/mdm/survivorship.py:145`; `edgar_warehouse/mdm/resolvers/base.py:108`]

### Pitfall 5: Letting Neo4j Scope Leak Into Phase 5

**What goes wrong:** `mdm run --entity-type all` may perform graph sync if Neo4j credentials are configured, which expands Phase 5 into Phase 7. [VERIFIED: `edgar_warehouse/mdm/pipeline.py:405`; `edgar_warehouse/mdm/pipeline.py:416`]

**Why it happens:** `MDMPipeline.run_all()` syncs graph nodes/edges when a Neo4j client is present. [VERIFIED: `edgar_warehouse/mdm/pipeline.py:416`]

**How to avoid:** Keep Phase 5 verification focused on entity loaders, or use commands/options that do not require graph sync. For `load-relationships`, use `--skip-graph-sync` when relationship code is touched for source validation only. [VERIFIED: `edgar_warehouse/mdm/cli.py:63`]

**Warning signs:** Tests require `NEO4J_URI`, `NEO4J_USER`, or `NEO4J_PASSWORD` for Phase 5. [VERIFIED: `.planning/workstreams/neo4j-pipe/ROADMAP.md`; `tests/mdm/conftest.py:120`]

## Code Examples

Verified patterns from existing code and official docs:

### Read Silver DuckDB as Read-Only

```python
# Source: edgar_warehouse/mdm/cli.py:250 and DuckDB Python Client API
import duckdb

con = duckdb.connect(path, read_only=True)
rows = con.execute("SELECT COUNT(*) FROM sec_company").fetchall()
```

DuckDB official Python API documents `connect(database=':memory:', read_only=False, config=None)` and says a file name plus `read_only` can be used when no changes are desired. [CITED: `https://duckdb.org/docs/current/clients/python/reference/`]

### Parse Ownership XML Through Existing Adapter

```python
# Source: edgar_warehouse/parsers/ownership.py:13
from edgar_warehouse.parsers.ownership import parse_ownership

parsed = parse_ownership(accession_number, xml_content, form_type)
owners = parsed["sec_ownership_reporting_owner"]
```

`parse_ownership()` wraps `edgar.ownership.Ownership.from_xml(content)` and emits silver table-shaped row dictionaries. [VERIFIED: `edgar_warehouse/parsers/ownership.py:13`; CITED: `https://edgartools.readthedocs.io/en/stable/parsing-filing-data/`]

### Open Primary Artifact From Registry

```python
# Source: edgar_warehouse/application/warehouse_orchestrator.py:2079
attachments = db.get_filing_attachments(accession_number)
primary = next((row for row in attachments if row.get("is_primary")), None)
raw_object = db.get_raw_object(str(primary["raw_object_id"]))
payload = read_bytes(str(raw_object["storage_path"]))
```

This pattern works for local fixture paths and S3 URIs because `read_bytes()` delegates remote paths through `fsspec`. [VERIFIED: `edgar_warehouse/infrastructure/object_storage.py:195`]

### Count Stable Domain Entities

```sql
-- Source: edgar_warehouse/mdm/database.py domain tables
SELECT 'company' AS kind, COUNT(*) FROM mdm_company
UNION ALL SELECT 'adviser', COUNT(*) FROM mdm_adviser
UNION ALL SELECT 'person', COUNT(*) FROM mdm_person
UNION ALL SELECT 'security', COUNT(*) FROM mdm_security
UNION ALL SELECT 'fund', COUNT(*) FROM mdm_fund;
```

Use this before and after a repeated fixture run to prove PIPE-02. [VERIFIED: `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md`; `edgar_warehouse/mdm/database.py`]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `parse-ownership-bronze` selects `form_type` and `period_of_report`. | Select `form` and `report_date` from `sec_company_filing`. | Current `silver_store.py` DDL in this worktree. [VERIFIED: `edgar_warehouse/silver_store.py:71`] | Planner must include a schema regression test. |
| Path-only bronze prefix listing for primary XML. | Prefer `sec_filing_attachment` -> `sec_raw_object` -> `read_bytes()`, with path fallback only when registry rows are absent. | Locked by Phase 5 context D-08. [VERIFIED: `05-CONTEXT.md`] | Local fixtures can exercise the same code path as S3. |
| `sec_tracked_universe` comments and older scripts. | `sec_company_sync_state` exists in silver DDL; MDM is the tracking source for warehouse runtime decisions. | Current DDL and application tests in this worktree. [VERIFIED: `edgar_warehouse/silver_store.py:351`; `tests/application/test_warehouse_orchestrator_mdm.py:1`] | MDM company loader should not require `sec_tracked_universe`. |
| Missing `MDM_SILVER_DUCKDB` handled after `_session()`. | Validate silver source first, then open MDM session only when source is ready. | Phase 5 requirement PIPE-03. [VERIFIED: `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md`] | Missing source tests can prove no DB mutation. |

**Deprecated/outdated:**

- `sec_tracked_universe` as a required current silver table is outdated for this phase. [VERIFIED: `rg sec_tracked_universe`; `edgar_warehouse/silver_store.py`]
- Direct SEC re-fetch during Phase 5 is out of scope. [VERIFIED: `05-CONTEXT.md`; `.planning/workstreams/neo4j-pipe/ROADMAP.md`]
- Direct bronze XML to MDM derivation is out of scope. [VERIFIED: `05-CONTEXT.md`]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Live S3 bronze primary XML availability was not verified during research; research relies on the milestone audit and code paths. [ASSUMED] | Open Questions / Summary | Planner may need an operator validation task before relying on real S3 bronze artifacts. |
| A2 | The minimal fixture can use synthetic SEC-like rows rather than real filings as long as it exercises the current silver schema and MDM resolvers. [ASSUMED] | Validation Architecture | If parser-specific behavior is required, planner must add one real sanitized Form 4 XML fixture. |

## Open Questions

1. **Are primary ownership XML artifacts present in the real target bronze root?**
   - What we know: Local silver candidates had nonzero Forms 3/4/5 filing metadata and zero parsed ownership rows. [VERIFIED: `.planning/workstreams/neo4j-pipe/v1.1-MILESTONE-AUDIT.md`]
   - What's unclear: This research did not query live S3 bronze. [ASSUMED]
   - Recommendation: Add a bounded operator validation task that reports counts for `sec_filing_attachment` primary rows joined to `sec_raw_object`, and only then runs repaired `parse-ownership-bronze`. [VERIFIED: `scripts/ops/check-neo4j-e2e.py:96`]

2. **Should `parse-ownership-bronze` get scope flags in Phase 5?**
   - What we know: Context gives the agent discretion to add `--limit`, `--cik-list`, `--accession-list`, or dry-run/report-only controls if needed. [VERIFIED: `05-CONTEXT.md`]
   - What's unclear: The roadmap success criteria do not require these flags. [VERIFIED: `.planning/workstreams/neo4j-pipe/ROADMAP.md`]
   - Recommendation: Add only `--limit` or `--accession-list` if tests or safe local verification need bounded execution. [ASSUMED]

3. **Should missing optional ADV tables block `mdm run --entity-type all`?**
   - What we know: Phase success expects company, adviser, person, security, and fund counts to stay stable across repeated runs. [VERIFIED: `.planning/workstreams/neo4j-pipe/ROADMAP.md`]
   - What's unclear: The production silver candidates in the audit focused on ownership gaps, not ADV row availability. [VERIFIED: `.planning/workstreams/neo4j-pipe/v1.1-MILESTONE-AUDIT.md`]
   - Recommendation: Make preflight table requirements entity-type aware; require ADV rows only when running adviser/fund loaders or `entity-type all`. [ASSUMED]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Isolated `workspace/neo4j-pipe` worktree | ISO-01 | yes | branch `workspace/neo4j-pipe` | None needed. [VERIFIED: `git worktree list`] |
| `uv` | Python execution and dependency groups | yes | 0.7.2 | None; project requires `uv`. [VERIFIED: `uv --version`; `AGENTS.md`] |
| Python via `uv run` | Repo runtime/tests | yes | 3.12.10 | None needed. [VERIFIED: `uv run python -c ...`] |
| AWS CLI | Optional S3-backed silver/bronze validation | yes | aws-cli/2.28.5 | Use local fixture if live AWS is unavailable. [VERIFIED: `aws --version`] |
| `ctx7` | Preferred library docs lookup | no | - | Official docs via web were used for DuckDB and edgartools. [VERIFIED: `command -v ctx7`; CITED: DuckDB/EdgarTools docs] |
| `duckdb` CLI | Not required; Python package is used | no | - | Use Python DuckDB through `uv run`. [VERIFIED: `command -v duckdb`; `uv run --extra ... python ...`] |
| `psql` / `pg_isready` | Optional live PostgreSQL diagnostics | no | - | Local tests use in-memory SQLite; live MDM requires `MDM_DATABASE_URL`. [VERIFIED: `psql --version`; `pg_isready`; `tests/mdm/conftest.py`] |
| `MDM_DATABASE_URL` | Live MDM CLI mutation | no | - | Unit/integration tests patch or use SQLite. [VERIFIED: environment probe; `tests/mdm/conftest.py`] |
| `MDM_SILVER_DUCKDB` | Live MDM silver source | no | - | Local fixture should set this per test. [VERIFIED: environment probe; `edgar_warehouse/mdm/cli.py:250`] |

**Missing dependencies with no fallback:**

- None for local planning and fixture tests. [VERIFIED: local commands]

**Missing dependencies with fallback:**

- `ctx7`, DuckDB CLI, `psql`, `pg_isready`, `MDM_DATABASE_URL`, and `MDM_SILVER_DUCKDB` are missing locally, but Phase 5 can use official docs plus local DuckDB/SQLite fixtures for automated tests. [VERIFIED: local commands]

## Validation Architecture

The workstream config does not set `workflow.nyquist_validation` to `false`, so validation is enabled. [VERIFIED: `.planning/workstreams/neo4j-pipe/config.json`]

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest, run through `uv`; tests currently need transient `--with pytest` if pytest is not installed in the uv environment. [VERIFIED: local command] |
| Config file | none found; tests are discovered under `tests/`. [VERIFIED: `find . -maxdepth 3 -name '*pytest*' -o -name 'conftest.py'`] |
| Quick run command | `uv run --extra mdm-runtime --extra s3 --with pytest pytest tests/mdm/test_source_to_mdm_load_path.py tests/application/test_parse_ownership_bronze.py -q` [ASSUMED proposed files] |
| Existing smoke command | `uv run --extra mdm-runtime --with pytest pytest tests/mdm/test_pipeline_relationships.py -q` passed 21 tests in 63.71s. [VERIFIED: local command] |
| Existing app command | `uv run --extra mdm-runtime --with pytest pytest tests/application/test_warehouse_orchestrator_mdm.py -q` passed 17 tests in 1.42s. [VERIFIED: local command] |
| Full suite command | `uv run --extra s3 --extra mdm-runtime --with pytest pytest tests/unit tests/architecture tests/application tests/mdm` [ASSUMED based on AGENTS.md test layout] |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| PIPE-01 | MDM reads local and URI-backed `MDM_SILVER_DUCKDB` without SEC fetch and loads all five entity domains. | integration | `uv run --extra mdm-runtime --extra s3 --with pytest pytest tests/mdm/test_source_to_mdm_load_path.py::test_mdm_run_all_from_silver_fixture -q` | no - Wave 0 [ASSUMED proposed file] |
| PIPE-01 | `parse-ownership-bronze` selects `form`/`report_date` and reads primary XML from artifact registry. | unit/integration | `uv run --extra s3 --with pytest pytest tests/application/test_parse_ownership_bronze.py -q` | no - Wave 0 [ASSUMED proposed file] |
| PIPE-02 | Re-running entity load against the same fixture keeps `mdm_company`, `mdm_adviser`, `mdm_person`, `mdm_security`, and `mdm_fund` counts stable. | integration | `uv run --extra mdm-runtime --with pytest pytest tests/mdm/test_source_to_mdm_load_path.py::test_entity_load_is_idempotent_for_domain_counts -q` | no - Wave 0 [ASSUMED proposed file] |
| PIPE-03 | Missing `MDM_SILVER_DUCKDB` exits nonzero with an actionable message before opening MDM session. | unit/CLI | `uv run --extra mdm-runtime --with pytest pytest tests/mdm/test_source_to_mdm_load_path.py::test_missing_silver_source_fails_before_session -q` | no - Wave 0 [ASSUMED proposed file] |
| ISO-01 | Phase files avoid loader-fix workstream and generated deployment JSON. | review/static | `git status --short` | manual/static [VERIFIED: AGENTS.md] |
| ISO-02 | Phase avoids gold/dbt/Step Functions/refactor surfaces. | review/static | `git diff --name-only` | manual/static [VERIFIED: AGENTS.md] |

### Sampling Rate

- **Per task commit:** Run the quick command for the files touched by that task. [ASSUMED]
- **Per wave merge:** Run existing MDM relationship smoke plus new Phase 5 tests. [ASSUMED]
- **Phase gate:** Run `uv run --extra s3 --extra mdm-runtime --with pytest pytest tests/unit tests/architecture tests/application tests/mdm` before `$gsd-verify-work`. [ASSUMED]

### Wave 0 Gaps

- [ ] `tests/application/test_parse_ownership_bronze.py` - covers current silver schema, skip already parsed accessions, artifact-registry primary XML reads, missing artifact reporting. [ASSUMED proposed file]
- [ ] `tests/mdm/test_source_to_mdm_load_path.py` - covers local/S3-like `MDM_SILVER_DUCKDB`, missing source before session, table/row preflight, and entity domain count idempotency. [ASSUMED proposed file]
- [ ] Fixture helper to create a tiny real DuckDB file using `SilverDatabase` DDL or direct DDL from `silver_store.py`, with synthetic rows for all five entity domains. [ASSUMED]
- [ ] Optional helper to seed in-memory MDM with `Base.metadata.create_all()` plus `seed_defaults(session)` so entity resolvers have source priorities and relationship definitions. [VERIFIED: `tests/mdm/conftest.py:101`; `edgar_warehouse/mdm/migrations/runtime.py:380`]

## Security Domain

Security enforcement is enabled by default because the workstream config does not explicitly disable it. [VERIFIED: `.planning/workstreams/neo4j-pipe/config.json`]

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no for Phase 5 local fixture path; yes for live AWS/S3 credentials outside test scope | Use existing AWS credential chain and `MDM_DATABASE_URL`; do not add new secret paths. [VERIFIED: `AGENTS.md`; `edgar_warehouse/infrastructure/object_storage.py`] |
| V3 Session Management | no | No browser/user session surface is involved. [VERIFIED: phase scope] |
| V4 Access Control | yes for storage/DB boundary | Reuse existing `object_storage` allowed protocols and existing MDM DB connection controls. [VERIFIED: `edgar_warehouse/infrastructure/object_storage.py:14`; `edgar_warehouse/mdm/database.py:73`] |
| V5 Input Validation | yes | Validate `MDM_SILVER_DUCKDB` presence, protocol/path, DuckDB openability, required tables, and required row counts before mutation. [VERIFIED: `edgar_warehouse/mdm/cli.py:250`; phase requirement PIPE-03] |
| V6 Cryptography | no new crypto | Do not alter S3/KMS/storage protections; use existing AWS path. [VERIFIED: `AGENTS.md`] |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Arbitrary URI/protocol read through `MDM_SILVER_DUCKDB` | Information Disclosure | Reuse `object_storage.read_bytes()` protocol allowlist and reject unsupported protocols. [VERIFIED: `edgar_warehouse/infrastructure/object_storage.py:14`] |
| Path traversal in storage paths | Tampering / Information Disclosure | Use existing `sanitize_relative_path()` and avoid ad hoc path construction for remote reads. [VERIFIED: `edgar_warehouse/infrastructure/object_storage.py:21`] |
| SQL injection through dynamic table validation | Tampering | Use a fixed allowlist of required table names; do not interpolate operator-controlled identifiers. [ASSUMED] |
| Partial MDM mutation after bad source | Tampering | Run silver preflight before `_session()` and before any resolver calls. [VERIFIED: `edgar_warehouse/mdm/cli.py:278`] |
| Secret leakage in CLI logs | Information Disclosure | Existing `_safe_arguments()` suppresses password/secret/token/key fields; keep source paths non-secret. [VERIFIED: `edgar_warehouse/mdm/cli.py:208`] |

## Sources

### Primary (HIGH confidence)

- `.planning/workstreams/neo4j-pipe/phases/05-source-to-mdm-load-path/05-CONTEXT.md` - locked decisions and phase boundaries. [VERIFIED: codebase grep]
- `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md` - PIPE/ISO requirements. [VERIFIED: codebase grep]
- `.planning/workstreams/neo4j-pipe/ROADMAP.md` - Phase 5 goal and success criteria. [VERIFIED: codebase grep]
- `.planning/workstreams/neo4j-pipe/v1.1-MILESTONE-AUDIT.md` - silver readiness gaps and local silver candidate counts. [VERIFIED: codebase grep]
- `AGENTS.md` - AWS focus, uv tooling, isolation, loader idempotency, ownership parser import constraint. [VERIFIED: codebase grep]
- `edgar_warehouse/application/warehouse_orchestrator.py` - `parse-ownership-bronze`, parse pipeline, silver hydration/publish. [VERIFIED: codebase grep]
- `edgar_warehouse/silver_store.py` - current silver DDL and merge methods. [VERIFIED: codebase grep]
- `edgar_warehouse/mdm/cli.py`, `edgar_warehouse/mdm/pipeline.py`, `edgar_warehouse/mdm/resolvers/*.py`, `edgar_warehouse/mdm/database.py` - MDM source reader, handlers, loaders, identity models. [VERIFIED: codebase grep]
- DuckDB Python Client API - `duckdb.connect(..., read_only=...)`. [CITED: `https://duckdb.org/docs/current/clients/python/reference/`]
- EdgarTools parsing docs - `edgar.ownership.Ownership.from_xml` for ownership XML. [CITED: `https://edgartools.readthedocs.io/en/stable/parsing-filing-data/`]

### Secondary (MEDIUM confidence)

- `scripts/ops/check-neo4j-e2e.py` and `scripts/ops/verify-counts.py` - operational readiness-count patterns; some live-probe logic appears diagnostic and should not define Phase 5 behavior. [VERIFIED: codebase grep]

### Tertiary (LOW confidence)

- Live S3 artifact availability was not queried; any claim about current live bronze data remains an assumption until an operator validation task runs. [ASSUMED]

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH - verified from `pyproject.toml`, `uv` metadata, and existing imports. [VERIFIED: local command]
- Architecture: HIGH - implementation boundaries are clear in existing command, storage, and MDM modules. [VERIFIED: codebase grep]
- Pitfalls: HIGH for schema/order/idempotency pitfalls found in code; MEDIUM for live artifact availability. [VERIFIED: codebase grep; `.planning/workstreams/neo4j-pipe/v1.1-MILESTONE-AUDIT.md`]

**Research date:** 2026-05-16
**Valid until:** 2026-06-15 for codebase-local findings; re-check live AWS/S3 data immediately before execution. [ASSUMED]
