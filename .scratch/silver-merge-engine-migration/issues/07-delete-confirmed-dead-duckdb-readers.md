# 07 — Delete the confirmed-dead local-DuckDB readers

**Type:** task

**Status:** resolved in code 2026-09-14, with a corrected scope (below). The two keep/delete
calls were the user's, made the same day.

## Question

Five modules read a local `SilverDatabase` that is never hydrated, with no scheduled presence
and no other map planning around them (checked 2026-09-13 against `deploy-aws-application.sh`
and every `.scratch/*/` map): `application/commands/validate_data_quality.py` (6 reads),
`application/commands/parse_adv_bronze.py` + `application/adv_bronze_discovery.py`,
`application/relationship_bulk_load.py`, `acquisition/capture_parity.py`. Delete them, same
discipline as duckdb-retirement-cutover Ticket 12: grep every caller first, confirm zero
scheduled presence, delete with their tests, remove CLI/registry entries.

Two to confirm rather than assume: `validate-data-quality` is named by one other map
(large-profile-unscoped-load-audit Ticket 03) — check whether that map still expects it;
`parse-ownership-bronze` IS in the deploy script, so it belongs to
[Ticket 06](06-submissions-and-artifact-tables-landing-only.md)'s reader sweep, not here.

**Blocked by:** none — frontier.

## Corrected scope (2026-09-14)

Every caller was checked before any edit, as Ticket 12 did. The premise held for two modules and
failed for two:

| Module | Finding | Outcome |
|---|---|---|
| `validate_data_quality.py` | No reference in `infra/`, `scripts/` or `.github/`. It hydrates the retired canonical `silver.duckdb`, so every check (row-count history, foreign keys, null ratios) reads a frozen snapshot, and the gold-vs-silver check compares live Snowflake gold with that snapshot. large-profile-unscoped-load-audit Ticket 03's "leave it as-is" covered only its memory risk, on a `build_source_export(db)` call that PR #550 had already removed. | **Deleted** (user decision). |
| `parse_adv_bronze.py` + `adv_bronze_discovery.py` | Not scheduled (the one `infra/` mention is a comment). Its default discovery (`sec_company_filing`, attachments, raw objects) and its `already_parsed` gate (`sec_adv_filing`) read the local store, so they are always empty. But `--artifact` still works: it reads staged ADV XML from bronze and lands rows through the run's landing export. Scheduled ADV is `fetch-adv-bulk` + `ingest-relationship-sources` (filings, per-fund rows) and `fetch-firm-roster` (fund counts); neither fills `sec_adv_office` or `sec_adv_disclosure_event`. | **Kept, `--artifact` only** (user decision): the two local reads are deleted. |
| `relationship_bulk_load.py` | Not a local reader. Its only store read is `insider_inventory`, called by `mdm verify-insider-coverage` with `pipeline.silver`, the Snowflake reader. The rest is pure functions used by `daily_artifact_resume` (inside `daily_incremental`), release mode, `batch_silver_resume` and four scripts. | Unchanged. |
| `capture_parity.py` | Not dead. `run_dual_path_filing_artifact_parity` is change-propagation Ticket 53's resolved result, wired to `compare-filing-artifact-capture --run-capture`; Ticket 06d already moved its `sec_raw_object` read onto the in-run lookup (same-run rows). The rest is used by `drive_filing_discovery` and `acceptance_evidence`. | Unchanged. |

`parse-ownership-bronze` stays with Ticket 06's reader sweep, as the question says.

## Implementation (resolved 2026-09-14 in code)

- **`validate-data-quality` deleted:** the command module, its CLI handler and parser, its
  registry, scope and dataset-catalog entries, and `test_validate_data_quality.py`.
  - `BookkeepingStore.get_recent_successful_pipeline_runs` had no other caller; deleted with its
    tests.
  - `test_bronze_anchor_agrees_with_validate_data_quality_fk_checks` deleted: its other side is
    gone, so `table_reconciliation/contracts.py` is now the only parent-link declaration (its
    docstring says so).
- **`parse-adv-bronze`, `--artifact` only:**
  - `discover_adv_bronze_artifacts(explicit_artifacts)` takes no store; the registry path,
    `_registry_candidate`, the accession filter and `source_kind` are gone.
  - `_run_parse_adv_bronze` no longer reads `sec_adv_filing`; `--artifact` is required.
  - `--limit` / `--accession-list` stay: they also filtered and capped named artifacts, so
    removing them would go past the "delete the no-argument mode" decision (caught by the Spec
    review; first removed, then restored).
  - Metrics `skipped` and `already_parsed` and the `parse_adv_bronze_skipped_already_parsed`
    event are gone (always 0 or never fired in production). A grep of `edgar_warehouse`,
    `tests`, `infra`, `docs`, `scripts` and `examples` found no consumer of them.
  - The old `already_parsed.add` never deduplicated repeats within one call (selection happened
    before parsing), so dropping it changes nothing; repeat rows collapse in dbt.
- **Docs:** `aws-mdm-source-to-mdm.md` Step 1b now points at the scheduled IAPD path first and
  shows only `--artifact`; `data-architecture.md` and `project-overview.md` rows updated.
  large-profile-unscoped-load-audit Ticket 03 has a dated note on the deletion.
- **Tests:** `test_parse_adv_bronze.py` and `test_adv_bronze_discovery.py` rewritten for the
  explicit-only contract; the fake store raises on any read. 7 tests were red first (local reads,
  missing `--artifact` requirement), plus 3 more for the restored `--limit`/`--accession-list`.
  Full suite excluding `tests/integration`: 3508 passed, 5 skipped. Ruff and mypy: nothing new
  against HEAD. Integration tests and dbt compile were not run locally.
- **Review (Standards, Spec, GoF).** GoF: no findings. Fixed:
  - stale `CLAUDE.md` caller note;
  - the Step 1b heading and troubleshooting row still called the step required, plus a doubled
    `)` in a link;
  - the docs overstated "only path" for offices and disclosure events (the configured-form parse
    pipeline also writes them for ADV-form accessions);
  - this ticket's claim that `--limit` / `--accession-list` only bounded the registry path;
  - the now-unused `skipped_non_adv` count, which made `_explicit_candidate` return three values.

  Declined:
  - renaming `missing_artifacts`, `explicit_artifacts` and the `parse_adv_bronze_*` events:
    log and metric consumers may key on them;
  - the ADR 0011 mention of `parse-adv-bronze`: ADRs are point-in-time records;
  - the `or []` on the dispatch's `artifacts`: programmatic `run_command` callers skip argparse;
  - `docs/CODEX.md` / `codex-fix-instructions.md` proposing the command: old task lists;
  - folding command registration (CLI, registry, dispatch, scope, catalog) into one spec
    object: real repeated change, but loud failures and `test_runtime_imports.py` already catch
    drift, and the restructure is far bigger than this ticket.
- **Nothing live owed:** both commands are unscheduled.
