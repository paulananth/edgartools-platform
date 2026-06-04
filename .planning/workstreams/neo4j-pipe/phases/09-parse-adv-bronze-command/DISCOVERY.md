---
phase: 09-parse-adv-bronze-command
type: discovery
topic: ADV bronze-to-silver parse command implementation
depth: standard
date: 2026-06-03
workstream: neo4j-pipe
confidence: high
---

# Parse ADV Bronze Command Discovery

## Summary

Phase 9 should implement `edgar-warehouse parse-adv-bronze` as the ADV counterpart to
`parse-ownership-bronze`, not as a new pipeline architecture. The repo already has the core pieces:
Phase 8 added `adv_bronze_discovery.py` for registry-backed and explicit-path bronze artifact
selection, `edgar_warehouse.parsers.adv.parse_adv(...)` returns rows for all four ADV silver tables,
and `SilverDatabase.merge_adv_*` methods already upsert those rows by table primary key.

The command should stay AWS/local and bronze-only on input. It must not fetch from SEC, list S3, run
gold/dbt, or require `SERVING_EXPORT_ROOT`/`MDM_DATABASE_URL`. The safest path is to mirror the
existing command registration and orchestrator branch for `parse-ownership-bronze`, then add focused
ADV tests for command wiring, registry reads, explicit artifact reads, skip behavior, parser errors,
missing/unreadable artifacts, and no SEC fetch helpers.

Context7 MCP is not exposed in this Codex session. External verification was limited to official
sources where current behavior matters: Python `argparse` command dispatch, DuckDB `ON CONFLICT`
upsert semantics, and SEC ADV family form context. The implementation decision is primarily
codebase-driven.

## Primary Recommendation

Implement a narrow `parse-adv-bronze` command with these surfaces:

1. Add CLI registration beside `parse-ownership-bronze` with `--limit`, `--accession-list`, and a
   repeatable explicit artifact fallback such as
   `--artifact ACCESSION,FORM,STORAGE_PATH[,CIK]`.
2. Add `edgar_warehouse/application/commands/parse_adv_bronze.py` and register
   `"parse-adv-bronze"` in `COMMAND_REGISTRY`.
3. Add a `_run_parse_adv_bronze(...)` branch in `warehouse_orchestrator.py` that:
   - fetches already parsed accessions from `sec_adv_filing`;
   - uses `discover_adv_bronze_artifacts(...)` and `read_adv_bronze_artifacts(...)`;
   - skips already parsed accessions before reading payloads where practical;
   - decodes payloads with UTF-8 replacement and calls `parse_adv(accession, content, form, cik)`;
   - merges `sec_adv_filing`, `sec_adv_office`, `sec_adv_disclosure_event`, and
     `sec_adv_private_fund`;
   - emits structured start, missing/unreadable, parse-error, skipped, and completed events;
   - populates metrics matching the ownership command style.
4. Add `_resolve_scope(...)` and path catalog support for the new command, mirroring
   `parse-ownership-bronze`.
5. Keep `parse-adv-bronze` out of `GOLD_AFFECTING_COMMANDS`,
   `SNOWFLAKE_EXPORT_COMMANDS`, and `SERVING_EXPORT_COMMANDS`.

## Alternatives Considered

### Reuse the generic parser pipeline

`_parse_filing_artifact(...)` already dispatches ADV forms to `parse_adv(...)` and writes the ADV
silver tables, but it reads primary artifacts only through the registry and is embedded in the
normal capture/parser policy path. It does not expose the Phase 8 explicit-artifact fallback and is
not a bounded ADV-only operator command. Reusing the merge snippet is useful; reusing the generic
pipeline as the command body is not enough for this milestone.

### Add a standalone command outside the orchestrator

This would reduce edits in `warehouse_orchestrator.py`, but it would bypass existing run
manifests, silver hydration/persistence, sync-run records, runtime settings, and command output
payloads. That is a worse fit for an operator command intended to behave like
`parse-ownership-bronze`.

### Do only registry-backed ADV parsing

That would satisfy the basic `--accession-list` and `--limit` CLI requirements, but it would leave
the Phase 8 explicit artifact fallback unreachable by operators. The live blocker includes the case
"bronze exists, no path exists to silver", so the command needs a bounded explicit existing-object
input.

## Key Findings

### Existing CLI and command registration pattern

- `edgar_warehouse/cli.py:144` routes `_handle_parse_ownership_bronze(...)` to
  `run_command("parse-ownership-bronze", args)`.
- `edgar_warehouse/cli.py:379` through `edgar_warehouse/cli.py:405` defines the ownership
  subparser with `--limit`, `--accession-list`, run-id support, and `set_defaults(handler=...)`.
- `edgar_warehouse/application/commands/parse_ownership_bronze.py:10` delegates to
  `run_command("parse-ownership-bronze", args)`.
- `edgar_warehouse/application/commands/__init__.py:25` through
  `edgar_warehouse/application/commands/__init__.py:42` holds the command registry.
- Python's official `argparse` docs confirm the repo's existing `add_subparsers(...)` plus
  `set_defaults(...)` style is a normal subcommand dispatch pattern:
  https://docs.python.org/3.12/library/argparse.html

### Existing orchestrator hook points

- `warehouse_orchestrator.py:1265` through `warehouse_orchestrator.py:1273` dispatches
  `parse-ownership-bronze` from `_capture_bronze_raw(...)`.
- `warehouse_orchestrator.py:1687` through `warehouse_orchestrator.py:1807` is the closest
  command-body pattern: fixed form query, already-parsed check, artifact read, parser call, merge
  calls, structured events, and metrics.
- `warehouse_orchestrator.py:3103` through `warehouse_orchestrator.py:3107` resolves command scope
  for manifests. `parse-adv-bronze` should get the same scope shape, extended with explicit artifact
  count or redacted artifact identifiers if useful.
- `dataset_path_catalog.py:259` special-cases `parse-ownership-bronze` as an operator command with
  bronze, staging, and artifacts manifests. `parse-adv-bronze` should be added there.

### Phase 8 discovery/read contract is the right input boundary

- `adv_bronze_discovery.py:10` defines the fixed ADV form allowlist:
  `ADV`, `ADV/A`, `ADV-E`, `ADV-E/A`, `ADV-H`, `ADV-H/A`, `ADV-NR`, `ADV-W`, `ADV-W/A`.
- `adv_bronze_discovery.py:50` through `adv_bronze_discovery.py:124` discovers candidates from
  `sec_company_filing`, registry attachments/raw objects, and explicit artifact records.
- `adv_bronze_discovery.py:127` through `adv_bronze_discovery.py:151` reads candidates through
  `object_storage.read_bytes` or an injected test double and records unreadable issues without
  aborting the batch.
- SEC's official Form ADV data page identifies the investment adviser registration/reporting family
  as Forms ADV, ADV-E, ADV-H, ADV-NR, and ADV-W:
  https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data

### Parser and silver merge behavior already exists

- `parsers/adv.py:31` through `parsers/adv.py:71` exposes
  `parse_adv(accession_number, content, form_type, cik=None)` and returns rows keyed by
  `sec_adv_filing`, `sec_adv_office`, `sec_adv_disclosure_event`, and `sec_adv_private_fund`.
- `parsers/__init__.py:21` through `parsers/__init__.py:30` already dispatches ADV forms to
  `parse_adv`.
- `warehouse_orchestrator.py:2520` through `warehouse_orchestrator.py:2529` shows the existing ADV
  parser invocation shape and merge sequence inside the generic parser path.
- `silver_store.py:175` through `silver_store.py:224` defines primary keys for the four ADV silver
  tables.
- `silver_store.py:1170` through `silver_store.py:1289` implements `merge_adv_*` methods with
  `ON CONFLICT ... DO UPDATE` upserts. DuckDB's official docs confirm `ON CONFLICT DO UPDATE`
  performs an update on conflicting primary or unique keys:
  https://duckdb.org/docs/sql/statements/insert

### Idempotency should combine skip and upsert

- Requirement ADV-05 says repeated runs skip already parsed ADV accessions by default.
- `sec_adv_filing` is the correct skip table because it has one row per accession and is the parent
  table for the ADV detail tables.
- The merge methods still provide a second idempotency layer if an accession is reprocessed through
  a future repair path.
- Phase 9 should define `--limit` as a cap on processable, not already skipped, accessions. If the
  current Phase 8 helper shape makes that inefficient, add a non-breaking optional exclusion
  parameter or filter before candidate reads in the command.

### Safety boundaries

- `warehouse_settings.py:11` through `warehouse_settings.py:23` lists commands that require
  serving export and MDM settings. `parse-adv-bronze` should not be added there.
- `warehouse_orchestrator.py:77` through `warehouse_orchestrator.py:89` defines gold and Snowflake
  export command sets. `parse-adv-bronze` should not be added there.
- Tests should patch `warehouse_orchestrator.download_sec_bytes` and
  `filing_artifact_service.refresh_filing_artifacts` with hard failures, following the Phase 8 and
  ownership test patterns.

## Code Examples

Recommended command-body skeleton for planning, not final code:

```python
def _run_parse_adv_bronze(*, db, sync_run_id, metrics, limit=None, accession_list=None, explicit_artifacts=None, **_):
    from edgar_warehouse.application.adv_bronze_discovery import (
        discover_adv_bronze_artifacts,
        read_adv_bronze_artifacts,
    )
    from edgar_warehouse.parsers.adv import parse_adv

    already_parsed = {
        row["accession_number"]
        for row in db.fetch("SELECT DISTINCT accession_number FROM sec_adv_filing")
    }
    discovered = discover_adv_bronze_artifacts(
        db,
        accession_list=accession_list,
        explicit_artifacts=explicit_artifacts,
        limit=None,
    )
    candidates = [
        candidate
        for candidate in discovered.candidates
        if candidate.accession_number not in already_parsed
    ]
    if limit is not None:
        candidates = candidates[:limit]

    read_result = read_adv_bronze_artifacts(candidates)
    for payload in read_result.payloads:
        candidate = payload.candidate
        parsed = parse_adv(
            candidate.accession_number,
            payload.payload.decode("utf-8", errors="replace"),
            candidate.form,
            candidate.cik,
        )
        db.merge_adv_filings(parsed.get("sec_adv_filing", []), sync_run_id)
        db.merge_adv_offices(parsed.get("sec_adv_office", []), sync_run_id)
        db.merge_adv_disclosure_events(parsed.get("sec_adv_disclosure_event", []), sync_run_id)
        db.merge_adv_private_funds(parsed.get("sec_adv_private_fund", []), sync_run_id)
```

Recommended explicit artifact parser shape:

```python
def _parse_adv_artifact(value: str) -> dict[str, str]:
    accession, form, storage_path, *rest = [part.strip() for part in value.split(",", 3)]
    artifact = {"accession_number": accession, "form": form, "storage_path": storage_path}
    if rest and rest[0]:
        artifact["cik"] = rest[0]
    return artifact
```

## Metadata

<metadata>
<confidence level="high">
The implementation path is confirmed by current repo code and official docs. Context7 was not
available in this runtime, but there is no unresolved external library decision. The only external
claims are backed by official Python, DuckDB, and SEC documentation.
</confidence>

<sources>
- Repo: `edgar_warehouse/cli.py`
- Repo: `edgar_warehouse/application/commands/__init__.py`
- Repo: `edgar_warehouse/application/commands/parse_ownership_bronze.py`
- Repo: `edgar_warehouse/application/warehouse_orchestrator.py`
- Repo: `edgar_warehouse/application/adv_bronze_discovery.py`
- Repo: `edgar_warehouse/parsers/adv.py`
- Repo: `edgar_warehouse/parsers/__init__.py`
- Repo: `edgar_warehouse/silver_store.py`
- Repo: `edgar_warehouse/infrastructure/dataset_path_catalog.py`
- Repo: `edgar_warehouse/infrastructure/warehouse_settings.py`
- Official Python argparse docs: https://docs.python.org/3.12/library/argparse.html
- Official DuckDB INSERT docs: https://duckdb.org/docs/sql/statements/insert
- Official SEC Form ADV data page: https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data
</sources>

<open_questions>
None.
</open_questions>

<validation_checkpoints>
- `edgar-warehouse --help` includes `parse-adv-bronze`.
- CLI parser accepts `parse-adv-bronze --limit N`, `--accession-list ...`, and repeated
  `--artifact ...` values.
- Command registry dispatches `"parse-adv-bronze"`.
- `_resolve_scope(...)` and `dataset_path_catalog.py` support `"parse-adv-bronze"`.
- Focused tests prove `download_sec_bytes` and `refresh_filing_artifacts` are not called.
- Focused tests prove registry and explicit artifact payloads call `parse_adv(...)` and all four
  `merge_adv_*` methods.
- Focused tests prove missing artifacts, unreadable artifacts, and parser exceptions are counted
  and do not abort remaining payloads.
- Idempotency tests prove accessions already present in `sec_adv_filing` are skipped by default and
  reruns do not duplicate `sec_adv_*` rows.
- Regression tests include Phase 8 discovery tests and existing `parse-ownership-bronze` tests.
</validation_checkpoints>
</metadata>
