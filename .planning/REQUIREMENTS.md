# Requirements: EdgarTools Platform

status: active
milestone: MDM & graph completeness
updated: 2026-05-15

---

## Section 1: Platform Baseline

These requirements describe constraints and invariants of the existing running platform. They
are treated as satisfied for the baseline system but must not be violated by any milestone work.

| ID | Description | Acceptance (abbreviated) |
|----|-------------|--------------------------|
| REQ-edgartools-version | edgartools >= 5.29.0 from PyPI, not vendored | `edgartools>=5.29.0` present via `uv sync`; batch scripts in scripts/batch/ rerun when version bumps |
| REQ-edgar-identity | EDGAR_IDENTITY env var must be set ("Name email@example.com") | Present before any CLI command; runtime validates at startup |
| REQ-warehouse-runtime-mode | WAREHOUSE_RUNTIME_MODE must be `bronze_capture` or `infrastructure_validation` | Runtime rejects unrecognized values |
| REQ-serving-export-root | SERVING_EXPORT_ROOT required for gold-affecting commands; must have trailing slash | Set before `gold-refresh` and any GOLD_AFFECTING_COMMANDS command; value ends with `/` |
| REQ-idempotent-loaders | Loaders skip existing bronze artifacts by default; re-fetch only on `--force` | Default: skip. `--force`: re-fetch. No SEC API calls for existing ownership XMLs unless forced |
| REQ-tracked-universe-seed | MDM universe seeded before first bootstrap run | `edgar-warehouse mdm seed-universe` completes; MDM_DATABASE_URL configured |
| REQ-phased-pipeline-for-scale | `bootstrap_phased` Step Function used for batch loads of 10+ companies | Batch loads >= 10 companies use Step Function; `bootstrap-next` reserved for single-CIK ad-hoc loads |
| REQ-gold-tables | 9 business tables + 1 status view in EDGARTOOLS_GOLD | All 10 objects present; business tables are dbt-managed dynamic tables with TARGET_LAG = DOWNSTREAM |
| REQ-snowflake-enterprise | Snowflake Enterprise+ required for CREATE DYNAMIC TABLE | Dynamic table creation succeeds during `dbt run` |
| REQ-mdm-env-vars | MDM_DATABASE_URL, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, MDM_API_KEYS required for MDM commands | All five env vars set; NEO4J_USERNAME from Aura mapped to NEO4J_USER |
| REQ-snowflake-account-format | SNOWFLAKE_ACCOUNT must be ORGNAME-ACCOUNTNAME format | Terraform and SnowCLI accept value without error |
| REQ-two-pass-snowflake-bootstrap | Snowflake native-pull bootstrap requires two AWS Terraform passes | `deploy-snowflake-stack.sh` automates two-pass sequence for dev |
| REQ-ecr-must-exist | ECR repos must exist before image push; MUTABLE tag setting required | Repos present in target account; `:dev` tag overwritable |
| REQ-snoccli-connection | SnowCLI connection named per environment in `~/.snowflake/config.toml` | `snow sql --connection edgartools-dev` succeeds |
| REQ-dashboard-prerequisites | Dashboard requires Python 3.11+, role grants on EDGARTOOLS_GOLD.*, config.toml | Snowflake role grants verified; config.toml present with correct database/schema |
| REQ-nfr-idempotency | All pipeline operations must be idempotent | Re-running any step produces no duplicates and does not fail on already-present artifacts |
| REQ-nfr-scale-performance | 100 companies in ~15 min via phased pipeline | `bootstrap_phased` completes in ~15 min; no gold builds during parallel bronze phase |
| REQ-nfr-no-secrets-in-terraform | No runtime secret values in Terraform state | `terraform plan` contains no plaintext secret values |
| REQ-nfr-bronze-immutability | Bronze Parquet files never mutated after write | No in-place overwrites; S3 versioning, encryption, public-access block remain enabled |
| REQ-nfr-azure-managed-identity | Azure storage uses managed identity authentication | No account keys, SAS tokens, or connection strings in any config or Terraform state |
| REQ-nfr-gold-cache-ttl | Streamlit dashboard queries cached 1 hour by default | All gold queries use `@st.cache_data(ttl=3600)` |

---

## Section 2: Milestone v1 — MDM & Graph Completeness

These requirements define what must be delivered and verifiable for the current milestone to be
complete. They are phase deliverables, not baseline constraints.

### Entity Resolution

#### REQ-MDM-01: Entity resolution produces deduplicated entities at scale

description: Running `mdm-run` against the full silver dataset (100+ companies) must produce
  a deduplicated, deterministic set of entities in the MDM PostgreSQL store. Re-running must
  not produce duplicate entities.

acceptance:
  - `edgar-warehouse mdm run` completes without error against full silver dataset
  - Entity count is stable on successive runs (idempotent)
  - No duplicate CIK-level records in MDM store after repeated runs
  - Completion time scales within `bootstrap_phased` Stage 2 time budget

phase: Phase 1

#### REQ-MDM-02: MDM universe seeded and tracking-status maintained

description: The canonical CIK universe is seeded in MDM and tracking statuses are maintained
  correctly (active, inactive, pending). The warehouse only processes CIKs with status `active`.

acceptance:
  - `edgar-warehouse mdm seed-universe` completes against MDM_DATABASE_URL
  - Active CIK list is the source of truth for bootstrap batch scope
  - Tracking status changes propagate to next pipeline run

phase: Phase 1

### Neo4j Graph Sync

#### REQ-MDM-03: Neo4j sync is idempotent and drift-free

description: Running `mdm-sync-graph` repeatedly against the same MDM state must produce
  identical graph node and edge counts each time. No ghost nodes or orphaned edges accumulate
  across runs.

acceptance:
  - `edgar-warehouse mdm sync-graph` completes without error
  - Node count and edge count are stable on successive runs against identical MDM state
  - `mdm-verify-graph` reports zero orphaned nodes after sync

phase: Phase 2

#### REQ-MDM-04: Graph connectivity verified end-to-end after each pipeline run

description: After each full phased pipeline run, `mdm-verify-graph` must be executable and
  must produce a structured report. The report must cover node counts, edge counts, and
  relationship integrity. Any defects found must be surfaced as clear operator messages.

acceptance:
  - `edgar-warehouse mdm verify-graph` runs to completion after `mdm-sync-graph`
  - Output includes node counts, edge counts, and relationship checks
  - Defects (orphaned reporters, missing edges) reported as named, actionable errors — not silent

phase: Phase 2

### Relationship Coverage

#### REQ-MDM-05: IS_INSIDER edges cover all Forms 3/4/5 reporters

description: Every person or entity that has filed a Form 3, 4, or 5 as a reporting person
  must be connected to the relevant issuer via an IS_INSIDER edge in Neo4j.

acceptance:
  - `mdm-backfill-relationships` runs after `mdm-run` without error
  - For every ownership record in silver with a reporter_cik, an IS_INSIDER edge exists in Neo4j
  - `mdm-verify-graph` confirms IS_INSIDER coverage matches ownership record count
  - Zero uncovered reporter-issuer pairs in the verify-graph report

phase: Phase 3

#### REQ-MDM-06: MANAGES_FUND edges cover all adviser-fund relationships

description: Every investment adviser in the MDM store that manages at least one private fund
  must be connected to each fund via a MANAGES_FUND edge in Neo4j.

acceptance:
  - `mdm-backfill-relationships` runs after `mdm-run` without error
  - For every adviser-fund pair in silver, a MANAGES_FUND edge exists in Neo4j
  - `mdm-verify-graph` confirms MANAGES_FUND coverage matches adviser-fund pair count
  - Zero uncovered adviser-fund pairs in the verify-graph report

phase: Phase 3

#### REQ-MDM-07: Relationship backfill is incremental and idempotent

description: Re-running `mdm-backfill-relationships` must not duplicate edges already present.
  It must process only new or changed relationships from the delta since the last run.

acceptance:
  - Re-running `mdm-backfill-relationships` produces no increase in IS_INSIDER or MANAGES_FUND
    edge counts when the underlying silver data has not changed
  - Relationship backfill completes in under 5 minutes for a 100-company dataset

phase: Phase 3

### Pipeline Hardening

#### REQ-PIPE-01: `--artifact-policy skip` is enforced in silver_mdm_gold pipeline

description: The silver_mdm_gold Step Function map must pass `--artifact-policy skip` to every
  `bootstrap-batch` invocation. This prevents the pipeline from making SEC API calls to
  re-fetch ownership XMLs that are already in S3 bronze.

acceptance:
  - Running `bootstrap_phased` does not make SEC API calls for previously-captured ownership XMLs
  - The `--artifact-policy skip` flag is present in the silver_mdm_gold Step Function definition
  - A test or operator verification step confirms the flag is not accidentally dropped on deploy

phase: Phase 4

#### REQ-PIPE-02: `GOLD_AFFECTING_COMMANDS` invariants are testable

description: The invariants that `bootstrap-batch` is NOT in `GOLD_AFFECTING_COMMANDS` and that
  `gold-refresh` IS in `GOLD_AFFECTING_COMMANDS` must be verifiable by running a command or
  script — not only by reading source code.

acceptance:
  - A script or test in `scripts/` or test suite asserts these invariants and exits non-zero if violated
  - CI or local validation run surface any regression immediately

phase: Phase 4

#### REQ-PIPE-03: Phased pipeline runs reliably at scale

description: The full `bootstrap_phased` Step Function must complete successfully for a
  100-company load, progressing through all three stages without manual intervention.

acceptance:
  - `bootstrap_phased` execution reaches SUCCEEDED state for a 100-company input
  - No stage silently skips due to upstream failure (each stage failure propagates explicitly)
  - Pipeline run time stays within 20 minutes for 100 companies

phase: Phase 4

---

## Traceability

| Requirement | Milestone | Phase | Status |
|-------------|-----------|-------|--------|
| REQ-MDM-01 | MDM & graph completeness | Phase 1 | Pending |
| REQ-MDM-02 | MDM & graph completeness | Phase 1 | Pending |
| REQ-MDM-03 | MDM & graph completeness | Phase 2 | Pending |
| REQ-MDM-04 | MDM & graph completeness | Phase 2 | Pending |
| REQ-MDM-05 | MDM & graph completeness | Phase 3 | Pending |
| REQ-MDM-06 | MDM & graph completeness | Phase 3 | Pending |
| REQ-MDM-07 | MDM & graph completeness | Phase 3 | Pending |
| REQ-PIPE-01 | MDM & graph completeness | Phase 4 | Pending |
| REQ-PIPE-02 | MDM & graph completeness | Phase 4 | Pending |
| REQ-PIPE-03 | MDM & graph completeness | Phase 4 | Pending |

Platform baseline requirements (Section 1) are treated as satisfied constraints for this
milestone. They are traced to LOCKED decisions in PROJECT.md but have no active phase
deliverable unless a regression is found.
