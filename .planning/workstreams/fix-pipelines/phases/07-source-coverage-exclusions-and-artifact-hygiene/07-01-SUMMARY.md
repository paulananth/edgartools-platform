---
phase: 07
plan: 01
subsystem: mdm-relationship-temporal-contract
tags: [mdm, postgres, temporal, conflict-resolution]
requires: [07-00]
provides: [relationship-logical-id, relationship-versioning, conflict-quarantine-policy]
affects: [07-02, 07-03, 07-04, 07-05, graph-sync]
key-files:
  created:
    - edgar_warehouse/mdm/migrations/006_relationship_temporal_contract.sql
    - tests/mdm/test_relationship_temporal_contract.py
  modified:
    - edgar_warehouse/mdm/database.py
    - edgar_warehouse/mdm/graph.py
    - edgar_warehouse/mdm/migrations/runtime.py
    - tests/mdm/test_runtime_ops.py
key-decisions:
  - relationship_id is a deterministic md5-derived value (not uuid.uuid5), so the Postgres
    migration's SQL-only backfill and the Python runtime path (database.relationship_logical_id)
    are byte-for-byte guaranteed to agree -- avoiding a silent logical-ID mismatch for
    pre-migration rows.
  - relationship_id is a SQLAlchemy context-sensitive column default, not merely an
    application-set field, so any direct ORM insert of MdmRelationshipInstance (pre-existing
    call sites in tests/mdm/test_api.py, tests/mdm/test_dashboard_readonly.py) still gets a
    correct value with no call-site changes required.
  - instance_id already served as this table's per-row identity, so the plan's "relationship
    version ID" concept is instance_id itself (documented via docstring), not a new column --
    avoids a redundant parallel ID.
  - Conflict resolution added a new mdm_relationship_source_priority table (keyed by
    rel_type_id, not entity_type like the pre-existing mdm_source_priority) since relationship
    conflict tie-breaks are a different axis from entity-resolution survivorship.
requirements-completed: [RTEMP-01, RTEMP-03, RTEMP-04, RLINE-01]
completed: 2026-07-13
---

# Phase 7 Plan 01: Relationship Identity, Temporal Contract, Conflict Policy

Resumed Codex's paused Phase 7 plan set (07-00 through 07-07 already written; 07-00
complete/human-approved) after Phase 6 closed, per explicit user direction to execute 07-01
inline rather than re-plan. The plan's assumed file names (`models.py`, `relationships.py`)
don't exist in this codebase -- relationship ORM models live in `database.py` and derivation
logic lives in `pipeline.py`; mapped both to their actual equivalents per 07-CONTEXT.md's
"agent's Discretion" section.

## Results

- `MdmRelationshipInstance` gains: `relationship_id` (immutable logical ID, deterministic),
  `valid_from_date`/`valid_to_date` (half-open, `CHECK (valid_to_date > valid_from_date)`),
  `date_provenance` (`reported`/`filing_date_proxy`/`unknown`), `relationship_kind`
  (`direct`/`derived`), `source_evidence` (JSON list), `superseded_by_version_id`,
  `quarantined`/`quarantine_reason`. All additive/nullable-or-defaulted; existing
  `effective_from`/`effective_to`/`source_system`/`source_accession` untouched.
- New `mdm_relationship_source_priority` table (per-rel-type source tie-break, lower
  priority number wins -- matches `mdm_source_priority`'s existing convention).
- `graph.py`'s `ensure_relationship` rewritten: identical evidence merges into
  `source_evidence` instead of duplicating rows; overlapping-but-differing evidence is
  resolved via the new priority table (loser superseded) or quarantined (no configured
  winner); non-overlapping date windows both remain current (e.g. two employment stints).
- New `close_relationship_version`/`supersede_relationship_version`/
  `quarantine_relationship_version` functions -- no delete function exists anywhere in the
  module (regression-tested).
- New Postgres migration `006_relationship_temporal_contract.sql`: guarded
  `ADD COLUMN IF NOT EXISTS`/`CREATE TABLE IF NOT EXISTS`, deterministic md5-based backfill
  of `relationship_id` for every pre-existing row, guarded `CHECK` constraint additions.
  Registered in `runtime.py`'s `migrate()`.

## Deviations from Plan

**[Rule 1 - Bug, caught before commit] SQL/Python relationship_id algorithm mismatch.**
First draft used `uuid.uuid5` in Python and planned `uuid_generate_v5` in SQL (needs the
`uuid-ossp` extension, not confirmed enabled). Switched both to a shared md5-hex-to-UUID
scheme so a row backfilled by the migration and a row later written by `ensure_relationship`
for the same triple always resolve to the identical `relationship_id`. Regression-tested
(`test_relationship_id_matches_sql_backfill_formula`).

**[Rule 1 - Bug, caught via full test-suite run] relationship_id NOT NULL broke existing
direct-insert call sites.** `tests/mdm/test_api.py` and `tests/mdm/test_dashboard_readonly.py`
construct `MdmRelationshipInstance` directly (not through `ensure_relationship`) and failed
with a NOT NULL constraint violation once `relationship_id` was added. Fixed by making it a
SQLAlchemy context-sensitive column default (`_default_relationship_id`, reads sibling
`rel_type_id`/`source_entity_id`/`target_entity_id` via `context.get_current_parameters()`)
rather than requiring every call site to set it explicitly. No test files needed modification.

**[Rule 3 - Scope] MDM_TABLES left unchanged.** Initially added
`mdm_relationship_source_priority` to `migrations/runtime.py`'s `MDM_TABLES` list, but this
broke `test_postgres_migration_covers_mdm_tables_without_tsql_tokens` (which asserts every
`MDM_TABLES` entry is defined in `001_initial_schema.sql`). Existing precedent
(`mdm_audit_firm`, added in migration 005) is also excluded from `MDM_TABLES` for the same
reason -- reverted to match that convention rather than change the test's contract.

## Verification

```text
uv run pytest tests/mdm/test_relationship_temporal_contract.py -q
18 passed

uv run pytest tests/mdm/ tests/architecture/ -q
363 passed, 1 failed (test_total_cik_limit_check_defaults_to_no_limit_sentinel --
pre-existing, unrelated to this plan; confirmed failing identically with this plan's
changes stashed out)

uv run pytest tests/ -q -x --ignore=tests/architecture/test_load_history_state_machine.py
609 passed
```

## Self-Check: PASSED

RTEMP-01, RTEMP-03, RTEMP-04, RLINE-01 complete. Plan 07-02 (exhaustive generation coverage
manifest, `valid_zero`, EDGE-07/08 exclusions) may begin.
