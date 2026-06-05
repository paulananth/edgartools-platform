# Phase 10: Live ADV Backfill Validation - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 10 delivers the first end-to-end operational proof that `parse-adv-bronze` (Phase 9) correctly populates silver ADV tables (`sec_adv_filing`, `sec_adv_private_fund`) and fully unblocks MDM adviser and fund entity loaders — including running the relationship pipeline through to Neo4j sync.

The phase runs locally against dev S3, local Colima Postgres, and local Colima Neo4j. It produces no new application code; all deliverables are operational: a validated pipeline run and a documented evidence artifact (`10-VALIDATION-NOTES.md`).

**In scope:**
- Pre-run selection of 50 ADV accessions from silver (with storage-path pre-filter)
- A deliberate failure test step (malformed accession → verify non-fatal error event)
- `parse-adv-bronze` sample run (50 accessions) with errors=0 success gate
- Silver row-count verification (`sec_adv_filing` and `sec_adv_private_fund` > 0)
- `mdm run --entity-type adviser` → write `mdm_adviser` rows to MDM Postgres
- `mdm run --entity-type fund` → write `mdm_fund` rows to MDM Postgres
- `edgar-warehouse mdm backfill-relationships` (relationship instances derived from mdm_fund)
- `edgar-warehouse mdm sync-graph` (sync to local Neo4j)
- `edgar-warehouse mdm verify-graph` (verify Neo4j state)
- MDM Postgres row-count verification (`mdm_adviser` > 0, `mdm_fund` > 0)
- Writing `10-VALIDATION-NOTES.md` with full evidence
- Updating `STATE.md` to reflect Phase 10 completion

**Out of scope:**
- Full corpus run (all ADV accessions — separate operator task)
- Any changes to `parse-adv-bronze`, ADV parser, or silver schema
- Gold refresh, dbt models, Snowflake sync (ISO-03)
- Docker Compose file creation
- SEC API calls (all bronze already captured)

</domain>

<decisions>
## Implementation Decisions

### Run Scope
- **D-01:** Sample size is `--limit 50`. Full corpus run is NOT part of Phase 10 — separate operator task after validation.
- **D-02:** Accessions are pre-selected (not alphabetical default). Use `--accession-list` with a comma-separated list derived from a pre-run silver query.
- **D-03:** Pre-selection query must JOIN `sec_company_filing → filing_attachments → raw_objects WHERE storage_path IS NOT NULL` to guarantee bronze artifacts exist. This avoids `parse_adv_bronze_missing_artifact` issues during the run.
- **D-04:** Pre-selection must explicitly include CIKs from: `SELECT cik, COUNT(*) FROM sec_company_filing WHERE form IN ('ADV','ADV/A') GROUP BY cik ORDER BY COUNT(*) DESC LIMIT 5`. High-volume ADV filers are almost always large advisers managing multiple private funds — guarantees `sec_adv_private_fund` will have rows.
- **D-05:** Total selected accessions: ~50, drawn from the top-5-by-count CIKs, filtered to those with confirmed storage paths.

### Fund Preflight
- **D-06:** Both `mdm run --entity-type adviser` AND `mdm run --entity-type fund` must pass. Running only adviser is not sufficient.
- **D-07:** MDM runs perform actual writes to MDM Postgres (not dry-run/preflight-only).
- **D-08:** After both MDM runs, verify `mdm_adviser` and `mdm_fund` row counts via direct Postgres query.

### Success Criteria (all gates must pass)
- **D-09:** `parse_adv_bronze_completed` event must show `errors=0`. Any parse error is a blocker — investigate and fix before declaring Phase 10 done. Swapping out failing accessions is acceptable only if the error is confirmed data-specific (not a parser bug).
- **D-10:** `SELECT COUNT(*) FROM sec_adv_filing` > 0 (silver DuckDB)
- **D-11:** `SELECT COUNT(*) FROM sec_adv_private_fund` > 0 (silver DuckDB) — guaranteed by D-04 accession selection
- **D-12:** `mdm run --entity-type adviser` exits 0 AND `SELECT COUNT(*) FROM mdm_adviser` > 0 (MDM Postgres)
- **D-13:** `mdm run --entity-type fund` exits 0 AND `SELECT COUNT(*) FROM mdm_fund` > 0 (MDM Postgres)
- **D-14:** `backfill-relationships` exits 0
- **D-15:** `sync-graph` exits 0
- **D-16:** `verify-graph` exits 0

### Evidence Format
- **D-17:** `10-VALIDATION-NOTES.md` is the primary evidence artifact. It must contain:
  1. The pre-selection DuckDB query and the resulting accession list
  2. The exact `edgar-warehouse parse-adv-bronze --accession-list ...` command and its terminal output (including the `parse_adv_bronze_completed` summary line)
  3. Silver row counts: `SELECT COUNT(*) FROM sec_adv_filing` and `SELECT COUNT(*) FROM sec_adv_private_fund`
  4. MDM run commands, exit codes, and `SELECT COUNT(*) FROM mdm_adviser / mdm_fund` results
  5. Relationship pipeline commands and outcomes
  6. A `## Phase 10 COMPLETE` declaration when all gates pass
  7. A `## Next Steps` section pointing to Phase 5 resume: `mdm-backfill-relationships → mdm-sync-graph → mdm-verify-graph` for the full adviser/fund graph (note: the Phase 10 run covers a 50-accession sample; full-scale graph sync is Phase 5 resume)
- **D-18:** `STATE.md` must be updated to reflect Phase 10 completion with row count summary.

### Environment (local Colima)
- **D-19:** All steps run locally: `edgar-warehouse` CLI on dev machine, `WAREHOUSE_STORAGE_ROOT=s3://edgartools-dev-warehouse-077127448006/warehouse`.
- **D-20:** Silver DuckDB is at `$WAREHOUSE_STORAGE_ROOT/silver.duckdb` (CLI syncs locally before reads/writes).
- **D-21:** MDM Postgres: `MDM_DATABASE_URL=postgresql://postgres:test@localhost:5432/mdm` (local Colima). Plan includes startup steps: `colima start` and the Postgres container `docker run` command.
- **D-22:** Neo4j: local Colima container (`NEO4J_URI=bolt://localhost:7687`). Plan includes startup steps.
- **D-23:** No VPN or port-forwarding to VPC services required.
- **D-24:** Plan starts with local environment startup steps (raw `docker run` commands, not a docker-compose file).

### Failure Testing and Remediation
- **D-25:** Phase 10 plan includes a deliberate failure test step: pass one known-bad/malformed accession via `--artifact` flag and verify the `parse_adv_bronze_error` event is emitted and the run continues processing remaining accessions. Proves non-fatal error handling works.
- **D-26:** If `backfill-relationships` or `sync-graph` fails: check Neo4j connectivity (`bolt://localhost:7687`), inspect the error message, fix the root cause, and re-run. Document retry behavior in VALIDATION-NOTES.
- **D-27:** For rollback of bad data: `DELETE FROM sec_adv_filing` and `DELETE FROM sec_adv_private_fund` in silver DuckDB; `DELETE FROM mdm_adviser` and `DELETE FROM mdm_fund` in MDM Postgres. Document these commands in the plan as a rollback section.

### Parser Library
- **D-28:** ADV parsing uses the `edgartools` PyPI package via `edgar_warehouse/parsers/adv.py` → `parse_adv()`. No changes to the parser; this is the existing Phase 9 implementation.

### Claude's Discretion
- If a parse error is investigated and determined to be data-specific (not a parser bug), Claude may swap the failing accession for another from the same CIK's filing list rather than blocking Phase 10.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### ADV Pipeline Core
- `edgar_warehouse/application/adv_bronze_discovery.py` — Discovery contract: `discover_adv_bronze_artifacts()` queries silver registry (not S3) to find ADV accessions with confirmed storage paths. Read this to understand the `--accession-list` and `--artifact` inputs.
- `edgar_warehouse/application/warehouse_orchestrator.py` lines 1821–1950 — `_run_parse_adv_bronze()` implementation. Idempotency logic, event emission, per-accession error handling.
- `edgar_warehouse/parsers/adv.py` — ADV parser using `edgartools`. `parse_adv(accession, content, form, cik)` returns dict with keys `sec_adv_filing`, `sec_adv_office`, `sec_adv_disclosure_event`, `sec_adv_private_fund`.

### MDM Preflight and Run
- `edgar_warehouse/mdm/cli.py` lines 338–490 — `_REQUIRED_TABLES_RUN` allowlist, `_validate_silver_tables()`, `_handle_mdm_run()`. Shows exactly which tables adviser/fund preflight checks and that `--entity-type all` skips ADV table enforcement.
- `edgar_warehouse/mdm/cli.py` lines 713–730 (sync-graph), 869–917 (verify-graph, backfill-relationships) — relationship pipeline command handlers.

### Silver Schema
- `edgar_warehouse/silver_store.py` lines 175–214 — `CREATE TABLE` DDL for `sec_adv_filing` and `sec_adv_private_fund`. Read column definitions before writing verification queries.
- `edgar_warehouse/silver_store.py` lines 1170–1300 — `merge_adv_*` methods: idempotent upsert logic used by the pipeline.

### Project Constraints
- `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md` — MDM-ADV-01, MDM-ADV-02, MDM-ADV-03 requirements that Phase 10 satisfies.
- `.planning/workstreams/neo4j-pipe/STATE.md` — Phase 10 status and milestone context.
- `CLAUDE.md` — `WAREHOUSE_STORAGE_ROOT`, `WAREHOUSE_BRONZE_ROOT`, `WAREHOUSE_RUNTIME_MODE`, `MDM_DATABASE_URL` env var definitions; isolation constraints ISO-01/02/03.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `discover_adv_bronze_artifacts(db, accession_list=..., limit=...)` — already handles the pre-selected accession list via `accession_list` arg. Pass the 50 selected accessions directly; no custom discovery code needed.
- `parse-adv-bronze --accession-list ACCESSIONS` — CLI flag accepts comma-separated accession numbers. This is the correct mechanism for the targeted 50-accession run.
- `parse-adv-bronze --artifact ACCESSION,FORM,STORAGE_PATH[,CIK]` — explicit artifact injection for the deliberate failure test step (pass a malformed accession).
- `_validate_silver_tables()` in `edgar_warehouse/mdm/cli.py:393` — MDM preflight validation already built and wired into `mdm run`. Preflight runs automatically before any MDM resolver.

### Established Patterns
- **Idempotency**: `_run_parse_adv_bronze` skips accessions already in `sec_adv_filing`. Re-running the same accession list is safe.
- **Non-fatal per-record errors**: `parse_adv_bronze_error` events are emitted per failing accession; the run continues. The `parse_adv_bronze_completed` summary event has `errors` count.
- **Storage path via registry**: Discovery does NOT scan S3. It uses `db.get_filing_attachments(accession)` → `db.get_raw_object(raw_object_id)` → `storage_path`. The storage path comes from the silver registry, populated during bronze capture.
- **`--entity-type all` does NOT enforce ADV tables**: The `all` mode excludes adviser/fund from the non-empty requirement. Always use `--entity-type adviser` and `--entity-type fund` explicitly for Phase 10.

### Integration Points
- **Silver DuckDB → ADV discovery**: `sec_company_filing` (ADV rows) → `filing_attachments` → `raw_objects` → `storage_path` → S3 read. The pre-selection query traverses this same chain.
- **Silver DuckDB → MDM preflight**: `_validate_silver_tables` opens silver and counts `sec_adv_filing` (for adviser) and `sec_adv_private_fund` (for fund).
- **MDM Postgres → Neo4j**: `backfill-relationships` derives relationship instances from `mdm_fund`/`mdm_security`, `sync-graph` pushes to Neo4j, `verify-graph` checks node/edge counts.

</code_context>

<specifics>
## Specific Ideas

- The pre-selection query (D-03/D-04) is a two-step DuckDB operation:
  1. Find top-5 CIKs by ADV filing count: `SELECT cik FROM sec_company_filing WHERE form IN ('ADV','ADV/A') GROUP BY cik ORDER BY COUNT(*) DESC LIMIT 5`
  2. For those CIKs, find accessions with confirmed storage paths (JOIN through filing_attachments → raw_objects WHERE storage_path IS NOT NULL AND is_primary = true), LIMIT 50
- The deliberate failure test (D-25) uses `--artifact "FAKE-ACCESSION-0,ADV,s3://invalid-path/fake.xml"` — a path that will fail S3 read, triggering `parse_adv_bronze_unreadable_artifact` rather than `parse_adv_bronze_error`. Verify the run continues to process the next artifact.
- Rollback commands (D-27): `duckdb $SILVER_PATH "DELETE FROM sec_adv_filing; DELETE FROM sec_adv_private_fund; DELETE FROM sec_adv_office; DELETE FROM sec_adv_disclosure_event"` and `psql $MDM_DATABASE_URL -c "DELETE FROM mdm_adviser; DELETE FROM mdm_fund"`.
- `edgartools` library used for ADV parsing — keep at current pinned version in `uv.lock`. Do not bump `edgartools` as part of Phase 10.

</specifics>

<deferred>
## Deferred Ideas

- **Full corpus ADV run** — Process all ADV accessions in silver without `--limit`. Separate operator task after Phase 10 validation succeeds.
- **docker-compose.yml for local services** — Consolidate Postgres + Neo4j startup into a compose file. Useful for all future phases; not in Phase 10 scope.
- **Phase 5 full-scale graph sync** — Running `backfill-relationships → sync-graph → verify-graph` across the complete adviser/fund universe. Phase 10 covers only the 50-accession sample. Full-scale sync is Phase 5 resume.
- **Automated regression test** — A pytest test with ADV XML fixtures that verifies `parse-adv-bronze` row counts. Deferred due to fixture management overhead; Phase 10 uses operational validation instead.

</deferred>

---

*Phase: 10-Live ADV Backfill Validation*
*Context gathered: 2026-06-04*
