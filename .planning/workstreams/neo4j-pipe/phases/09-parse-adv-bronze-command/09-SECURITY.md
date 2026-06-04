---
phase: 09
slug: parse-adv-bronze-command
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-03
register_authored_at_plan_time: true
---

# Phase 9 - Security

Per-phase security contract for the ADV bronze-to-silver parse command.

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Operator CLI to warehouse runtime | `edgar-warehouse parse-adv-bronze` accepts bounded operator inputs and dispatches through the warehouse command runner. | Accession filters, explicit artifact metadata, run id |
| Warehouse runtime to object storage adapter | The parse command reads existing bronze objects through the storage adapter and does not call SEC download helpers. | Bronze storage paths and raw filing bytes |
| Bronze payload to ADV parser to silver store | Untrusted SEC filing bytes are decoded and parsed into fixed silver ADV tables. | ADV XML/text payloads and structured ADV rows |
| Command classification to runtime settings | The command name controls whether gold, Snowflake, and serving export settings are required. | Runtime command name and settings requirements |

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-09-01 | Network side effects / SSRF | `parse-adv-bronze` runner | mitigate | Command uses Phase 8 bronze discovery plus `read_adv_bronze_artifacts(..., read_bytes_fn=read_bytes)`; no SEC download or filing refresh helpers are called. Tests patch `download_sec_bytes` and `refresh_filing_artifacts` to fail if invoked. | closed |
| T-09-02 | Input validation / injection | CLI explicit artifact input | mitigate | CLI parses `--artifact` into fixed fields, discovery enforces the ADV-family form allowlist, storage paths are passed only to the object storage adapter, and writes use fixed `merge_adv_*` table methods rather than dynamic SQL/table names. | closed |
| T-09-03 | Integrity / idempotency | ADV silver merge path | mitigate | The runner loads already parsed accessions from `sec_adv_filing`, skips them before storage reads, and writes parsed data through existing ADV merge/upsert methods. | closed |
| T-09-04 | Configuration / privilege creep | Runtime settings and export classification | mitigate | `parse-adv-bronze` is not included in gold, Snowflake, or serving export command sets, so the command does not require export roots or broadened runtime settings. | closed |

## Evidence

| Control | Evidence |
|---------|----------|
| No SEC network fetch path | `tests/application/test_parse_adv_bronze.py` defines `no_sec_fetch`, patching `download_sec_bytes` and `refresh_filing_artifacts` to raise. The focused test suite passes with those guards active. |
| Bronze-only storage read | `edgar_warehouse/application/warehouse_orchestrator.py` routes `parse-adv-bronze` to `_run_parse_adv_bronze`, which discovers candidates, skips already parsed accessions, and reads selected candidates through `read_adv_bronze_artifacts(..., read_bytes_fn=read_bytes)`. |
| Explicit artifact validation | `edgar_warehouse/cli.py` accepts repeatable `--artifact ACCESSION,FORM,STORAGE_PATH[,CIK]`; `adv_bronze_discovery.py` rejects missing accessions, empty storage paths, and non-ADV forms before creating candidates. |
| Idempotent silver writes | `_run_parse_adv_bronze` queries `sec_adv_filing` for existing accessions before reads and writes parsed rows through `merge_adv_filings`, `merge_adv_offices`, `merge_adv_disclosure_events`, and `merge_adv_private_funds`. |
| Export settings isolation | `GOLD_AFFECTING_COMMANDS`, `SNOWFLAKE_EXPORT_COMMANDS`, and `SERVING_EXPORT_COMMANDS` do not include `parse-adv-bronze`; `rg -n "parse-adv-bronze" edgar_warehouse/infrastructure/warehouse_settings.py` found no matches. |
| Verification run | `uv run --extra s3 --with pytest pytest tests/application/test_parse_adv_bronze.py -q` passed: 8 tests, 3 upstream `edgartools` deprecation warnings. |

## Accepted Risks Log

No accepted risks.

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-03 | 4 | 4 | 0 | Codex inline security audit |

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-03
