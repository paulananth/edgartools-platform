---
phase: 07
plan: 06
subsystem: silver-publication-safety
tags: [silver, duckdb, s3, object-storage, bronze, idempotency, repair-audit]
requires: []
provides: [protected-table-registry, semantic-silver-merge, staged-optimistic-promotion, bronze-repair-audit]
affects: [warehouse_orchestrator.py, object_storage.py, bronze_filing_artifacts.py]
key-files:
  created:
    - edgar_warehouse/silver_protection.py
  modified:
    - edgar_warehouse/application/warehouse_orchestrator.py
    - edgar_warehouse/infrastructure/object_storage.py
    - edgar_warehouse/infrastructure/filing_artifact_service.py
    - edgar_warehouse/bronze_filing_artifacts.py
    - tests/application/test_warehouse_orchestrator_mdm.py
    - tests/unit/test_loader_idempotency.py
    - .planning/workstreams/fix-pipelines/REQUIREMENTS.md
key-decisions:
  - The protected-table registry (edgar_warehouse/silver_protection.py) is a new,
    standalone module rather than inline code in warehouse_orchestrator.py or a
    change to silver_store.py's DDL. It reviews and classifies all 22 canonical
    domain tables (business keys + an optional provenance authority column
    mirroring each table's existing last_synced_at/ingested_at/fetched_at
    column) plus 11 explicitly-excluded operational/checkpoint tables (schema_
    migration, sec_parse_run, sec_company_sync_state, etc.). A table present in
    either database that is neither classified nor excluded fails the whole
    merge closed -- there is no default "just overwrite" path for anything new.
  - merge_candidate_into_canonical() starts the output as an exact byte copy of
    canonical (via shutil.copy2), then only INSERTs new business keys and
    UPDATEs same-key rows whose declared authority column strictly favors the
    candidate -- it never DELETEs, so a partial candidate can never regress
    canonical coverage. A same-key conflict with no declared authority column,
    or a tied/null authority value on either side, is never resolved silently:
    it is collected and raises SemanticMergeConflictError with the full
    row-level report (table, business key, both sides' values, differing
    columns) once every table has been processed.
  - Schema evolution through ordinary merge is additive-only: a candidate may
    declare extra columns (added via ALTER TABLE ADD COLUMN IF NOT EXISTS) but
    may never drop a canonical column or change a shared column's declared
    type -- both raise SilverPublicationError. Genuinely destructive schema/key
    changes go through the separate execute_silver_repair()/plan_silver_repair()
    contract instead: it requires a non-empty operator identity AND reason
    (SilverRepairRequiresReasonError otherwise), always computes and returns a
    SchemaDiff (dropped columns, type changes, business-key change) via a
    dry_run=True default that never mutates output_path, and only replaces the
    table (CREATE OR REPLACE via a full read of the candidate) when explicitly
    invoked with dry_run=False. This is a distinct code path from ordinary
    publish/merge and from --force -- there is no flag on the merge path that
    reaches it.
  - object_storage.StorageLocation gained read_object_version/write_staged_bytes/
    promote_staged. Local (non-remote) storage has no real S3 object versioning,
    so read_object_version computes an MD5 content digest as a deterministic
    stand-in (matching S3's own default single-part-upload ETag scheme) --
    letting the exact same compare-before-promote code path be exercised with
    real files in local/dev/test runs, not just mocked for "remote". Remote
    storage reads the real ETag/VersionId via fsspec's fs.info(). promote_staged
    re-reads canonical's current version immediately before committing and
    raises PromotionConflictError (never deleting the staged object) if it no
    longer matches the caller's baseline -- a concurrent writer between the
    baseline read and promotion is caught, not silently last-writer-wins.
  - _publish_silver_database_if_remote is rewritten around this: read canonical's
    baseline version once, download+merge only if canonical already exists
    (skip the merge entirely on a genuinely first-ever publish), stage the
    merged/candidate bytes under an immutable random-token key, then promote
    only if canonical's version is unchanged. The write-record dict gained
    source_version, staged_checksum, canonical_version, and tables_merged so
    a publish's provenance is inspectable. There is no force parameter on this
    function at all -- structurally, nothing can bypass the merge or the
    concurrency check.
  - Bronze repair-audit scope was deliberately narrowed from a hard requirement
    to an additive one after discovering the two existing warehouse_orchestrator.py
    call sites (filing_artifact_pipeline and one other) already invoke
    refresh_filing_artifacts(force=force) today with no operator/reason concept,
    and neither warehouse_orchestrator.py nor cli.py is in this plan's declared
    files_modified list. Requiring a non-empty operator/reason whenever
    force=True (my first draft) would have raised ValueError on every existing
    production --force invocation. Instead, fetch_filing_artifacts gained
    optional operator/reason kwargs (threaded through filing_artifact_service.
    refresh_filing_artifacts); a repair_audit list entry (accession,
    prior/replacement object hash + storage path, operator, reason) is emitted
    whenever force=True actually replaces a document that had a prior raw
    object -- using operator=None/reason=None (not a fabricated value) for
    callers that haven't been updated to supply them yet. Wiring an explicit
    --operator/--reason CLI flag through warehouse_orchestrator.py/cli.py is a
    follow-up, out of this plan's declared scope, and is called out as a caveat
    in REQUIREMENTS.md rather than silently left unstated.
  - DEF 14A and 13F-HR idempotency coverage: the existing test file had ownership-
    form and 13F-HR *cold-start* (force=True, fallback-discovery) cache tests but
    zero DEF 14A tests and zero 13F-HR *cache-hit* (attachments already captured,
    force=False) tests. Both gaps are closed with regression tests asserting
    network_fetches == 0 and no download_bytes/get_filing invocation, matching
    the plan's explicit "Add DEF 14A and 13F command integration cases."
requirements-completed: [ARTF-01, ARTF-02]
requirements-partially-addressed: []
completed: 2026-07-15
---

# Phase 7 Plan 06: Semantic Silver Merge, Staged Optimistic Promotion, and Audited Bronze Repair

## Results

**Task 1 (protected-table registry + semantic silver merge):**
- New `edgar_warehouse/silver_protection.py`: `PROTECTED_TABLE_REGISTRY` classifies
  all 22 canonical domain tables from `silver_store.py`'s DDL with business keys and
  (where the table already has one) a provenance authority column; `EXCLUDED_OPERATIONAL_TABLES`
  explicitly excludes the 11 checkpoint/run-tracking/staging tables. Any table present
  in candidate or canonical that is neither classified nor excluded fails the merge
  closed.
- `merge_candidate_into_canonical()`: copies canonical to the output path unchanged,
  then only inserts new business keys and updates same-key rows the declared authority
  column favors — it never deletes a canonical-only row, so a partial candidate cannot
  regress coverage. Same-key conflicts with no authority column, or a tied/null
  authority value, raise `SemanticMergeConflictError` with a full row-level report
  (table, key, both sides' values, differing columns) rather than picking a side.
- Schema evolution through ordinary merge is additive-only (extra candidate columns are
  added via `ALTER TABLE ADD COLUMN IF NOT EXISTS`); a dropped canonical column or a
  changed column type raises `SilverPublicationError` instead.
- Destructive changes go through a separate `execute_silver_repair()`/`plan_silver_repair()`
  contract: requires a non-empty operator + reason, always computes a `SchemaDiff`
  (dropped columns, type changes, business-key change) via a `dry_run=True` default that
  never mutates output, and only replaces the table when explicitly invoked with
  `dry_run=False`.

**Task 2 (staged optimistic S3 promotion):**
- `StorageLocation.read_object_version`/`write_staged_bytes`/`promote_staged` added to
  `object_storage.py`. `read_object_version` reads the real S3 ETag/VersionId via
  `fsspec`'s `fs.info()` for remote storage, or an MD5 content digest for local storage
  (deterministic, exercisable in tests without S3). `write_staged_bytes` writes under a
  fresh random-token key that never collides with the canonical key. `promote_staged`
  re-reads canonical's version immediately before committing and raises
  `PromotionConflictError` — leaving the staged object in place for inspection/retry —
  if it no longer matches the caller's baseline.
- `_publish_silver_database_if_remote` rewritten: reads canonical's baseline version
  once; merges only if canonical already exists (skipped entirely on a first-ever
  publish); stages the merged bytes; promotes only if canonical is unchanged. The
  write-record dict gained `source_version`, `staged_checksum`, `canonical_version`, and
  `tables_merged`. There is no `force` parameter anywhere on this path.

**Task 3 (bronze cache idempotency + audited repair):**
- Added a DEF 14A cache-hit regression test and a 13F-HR cache-hit regression test
  (previously only 13F-HR *cold-start* fallback-discovery was covered) to
  `tests/unit/test_loader_idempotency.py`, both asserting `network_fetches == 0` and no
  `download_bytes`/`get_filing` invocation.
- `fetch_filing_artifacts` gained optional `operator`/`reason` kwargs, threaded through
  `filing_artifact_service.refresh_filing_artifacts`. When `force=True` actually replaces
  a document that had a prior raw object, a `repair_audit` entry is emitted: accession,
  prior/replacement object hash + storage path, operator, reason. `force=True` against a
  genuinely first-time fetch (no prior raw object) emits no fabricated audit entry.
  Existing callers that don't yet pass operator/reason still get a truthful record with
  those fields `None`, not a made-up value.
- The existing no-throttle-sleep-on-cache-hit behavior (`network_fetches` gating the
  orchestrator's per-accession sleep) is untouched and re-verified by the new tests.

## Deviations from Plan

**[Rule 3 - Scope] Bronze `--force` audit-record scope narrowed from "always require
operator/reason" to "always emit an honest record, requiring them only where already
wired."** The plan's Task 3 `files_modified` lists only `filing_artifact_service.py`,
`bronze_filing_artifacts.py`, and the test file — not `warehouse_orchestrator.py` or
`cli.py`. Two existing call sites in `warehouse_orchestrator.py` already invoke
`refresh_filing_artifacts(force=force)` with no operator/reason concept at all. A first
draft made a non-empty operator+reason a hard requirement whenever `force=True`, which
would have raised `ValueError` on every one of those existing call sites (and on 3
pre-existing tests in `test_loader_idempotency.py` that pass `force=True` with neither).
Caught before it became a real regression — reverted to optional kwargs that still
produce a fully-populated, honest audit record (`operator`/`reason` `None` when not
supplied, never fabricated). CLI-level `--operator`/`--reason` flag wiring through
`warehouse_orchestrator.py`/`cli.py` is a follow-up, not done here, and is stated as a
caveat in `REQUIREMENTS.md` rather than left as a silent gap.

**[Rule 2 - Blocker, resolved] DuckDB does not support `<catalog>.information_schema.
table_constraints`/`key_column_usage` cross-catalog qualification** (unlike
`information_schema.tables`/`columns`, which do work qualified that way — confirmed by
direct testing). `plan_silver_repair`'s business-key diff switched to
`duckdb_constraints()` filtered by `database_name`/`table_name`/`constraint_type`, using
its `constraint_column_names` array column instead of joining `table_constraints` to
`key_column_usage`.

## Verification

```text
uv run pytest tests/application/test_warehouse_orchestrator_mdm.py -k 'publish or merge or conflict or schema' -q
15 passed

uv run pytest tests/application/test_warehouse_orchestrator_mdm.py -k 'etag or version or promote or repair' -q
8 passed

uv run pytest tests/application/test_warehouse_orchestrator_mdm.py -q
47 passed

uv run pytest tests/unit/test_loader_idempotency.py -q
14 passed

uv run --extra s3 --extra snowflake --extra mdm pytest tests/ -q --ignore=tests/architecture/test_load_history_state_machine.py
759 passed (up from 733 before this plan; +26 new tests, 0 regressions)
```

## Self-Check: PASSED

ARTF-01 and ARTF-02 both complete. Ordinary silver publication is now monotonic
(protected business keys cannot be lost through a partial/stale candidate, unclassified
tables and destructive schema/key changes fail closed, `--force` has no bypass on this
path) and concurrency-safe (staged upload + version/ETag compare-before-promote catches
a concurrent canonical write instead of silently last-writer-wins). Bronze artifact
idempotency is now asserted for DEF 14A and 13F-HR cache hits alongside the pre-existing
ownership-form coverage, and `--force` repairs emit a truthful accession/prior-hash/
replacement-hash/operator/reason audit record at the service boundary — with CLI-level
operator/reason flag wiring explicitly named as a follow-up rather than silently assumed
done. This closes Phase 7's artifact-hygiene goal; Plan 07-07 (bounded dev rehearsal)
remains unexecuted pending explicit user direction.
