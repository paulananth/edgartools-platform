# 11 — Restore release-mode Branch B same-run reads

**Type:** grilling

**Status:** resolved in code 2026-09-14: release mode retired (user decision). Takes effect in prod on the next `deploy-aws-application.sh` run.

## Question

Ticket 06d made `sec_company_filing`, `sec_filing_attachment` and `sec_raw_object` landing-only.
Same-run reads through `get_filing`/`get_filing_attachments`/`get_raw_object` answer from the
in-run lookup ([ADR 0011](../../../docs/adr/0011-same-run-silver-reads-from-recorded-rows.md)), but
raw SQL on the local store now finds nothing.

`bootstrap-batch --release-mode` (the `one_click_data_refresh` strict candidate-manifest Map)
captures submissions and artifacts, then `_run_release_branch_b_parsers` passes the local
`SilverDatabase` as `source` to `run_bootstrap_fundamentals_per_filing` and
`run_bootstrap_thirteenf`. Those query the three tables with raw SQL
(`fundamentals_ingest.py`: `cik IN ... AND form IN ...` on filings, then attachments and raw
objects by key). Before 06d they saw this run's rows in local DuckDB; after 06d they fail closed
with "required candidates missing from filing manifest". Found during 06d implementation, not
by its grilling. Its tests use hand-rolled `fetch()` stubs, so none of them caught it.

The last two `one_click_data_refresh` executions (2026-09-06) ran with `release_mode: false`, so
the path is dormant, not actively failing.

Options:

- Give `fundamentals_ingest` a reader interface instead of raw SQL (filings by CIKs and forms,
  attachments by accession, raw object by id), answered by the in-run lookup locally and by
  the Snowflake reader in `bootstrap-fundamentals`.
- Retire release-mode Branch B if the strict release Map is no longer used.
- Something else.

**Blocked by:** none — frontier.

## Answer (2026-09-14)

**Decision (user): release mode is not needed; retire it**, rather than rebuilding Branch B's reads.
Facts behind it:
- The strict path of `one_click_data_refresh` last ran 2026-07-18 to 07-25 for release-readiness
  Ticket 20 (technical PASS 07-25). The two runs on record since (2026-09-06) used
  `release_mode: false`; no schedule starts it.
- It was broken at both ends: the manifest freeze (`build_relationship_release_manifest.py`) read
  the retired canonical `silver.duckdb`, and Branch B's raw SQL on the local store finds nothing
  since 06d.

**Deleted:**
- the strict path of `one_click_data_refresh` in `deploy-aws-application.sh` (`ReleaseModeCheck`
  and every `Strict*` state); the machine now starts at `ResumeFromRunIdPresenceCheck`;
- `reconcile-relationship-release` (command module, CLI, registry, dispatch, scope, dataset catalog);
- `bootstrap-batch --release-mode/--candidate-manifest/--repair-manifest`, `bootstrap-fundamentals
  --release-mode/--candidate-manifest`, and the `branch_b_deferred` parser policy;
- in `warehouse_orchestrator.py`: the release block of `bootstrap-batch` (manifest load, completion
  ledger, batch and accession done markers), `_run_release_branch_b_parsers`, the `release_mode` /
  `repair_manifest_accessions` parameters and branches of `_run_submissions_bronze_then_silver` and
  `_run_configured_form_artifact_pipeline`, `candidate_outcomes`, the `WAREHOUSE_RELEASE_ARTIFACT_*`
  settings, and `_run_parse_pipeline`'s release-only `fail_closed`;
- `release_mode` / `candidate_accessions` in `fundamentals_ingest.py`;
- the release-only functions of `relationship_bulk_load.py` (1605 to 243 lines);
- four operator scripts (`build_relationship_release_manifest.py`, `validate_relationship_release_manifest.py`,
  `build_ticket20_strict_execution_input.py`, `build_remaining_release_batches.py`) and their tests.

**Kept:** daily incremental's recurring mode (the shared branches now test `recurring_mode` only);
`relationship_bulk_load.py`'s batch identity / remaining-batch helpers (`batch_silver_resume`),
`sanitize_accession_for_path` (`daily_artifact_resume`), and the insider-coverage functions behind
`mdm verify-insider-coverage` (kept as a general MDM check, user decision); `ecr_rollback_cli.py`,
`build_13f_filer_list.py --release-mode` and `scripts/ops/watch_release.py` (same word, unrelated).
Release-readiness evidence docs and ADR 0011 are point-in-time records and stay.

**Tests:** `tests/unit/test_release_mode_retired.py` (red first: CLI flags and command rejected,
`branch_b_deferred` unsupported, release parameters gone, no strict states). The five release
artifact-retry tests that covered the shared retry loop now run in recurring mode; release-only
tests were deleted; `test_release_batch_resume.py` became `test_cik_batch_resume_helpers.py`
(kept helpers only).
Full suite excluding `tests/integration`: 3432 passed, 5 skipped. The review fixes below landed
after that run started; `tests/mdm` (796 passed) and the touched test files (168 passed) were re-run
afterwards. Integration tests and dbt compile were not run locally.

**Review (Standards, Spec, GoF).** GoF: no findings (with release mode gone the artifact
pipeline has one mode left, so no policy object is warranted; `relationship_bulk_load.py`'s name no
longer fits its two remaining groups, a rename worth doing only when they are next touched).
Both Standards and Spec found, and this ticket fixed:
- `mdm build-relationship-release-manifest` was still registered and imported the deleted script
  (`ModuleNotFoundError` when run); its parser and handler are deleted, with a test;
- `install.sh`'s `one_click_data_refresh` stage still said the input must carry
  `"release_mode": false` for a `ReleaseModeCheck` state that no longer exists;
- the deploy script's `BOOKKEEPING_DATABASE_URL` comment named the deleted command as its reason;
  the injection stays (removing it changes MDM task definitions), and the comment now says so;
- stale wording in `adv_bulk_fetch.py`, `test_batch_silver_resume.py`, two orchestrator regression
  notes, and the now-unused `BRANCH_B_13F_FORMS` constant.

Both reviews confirmed recurring-mode behaviour is unchanged hunk by hunk, and the generated
`one_click_data_refresh` definition resolves every `Next`/`Default`/`Catch` target.

**Lint and types:** mypy has no new errors on the changed modules (37 before, 20 after). Ruff reports six new BLE001
(blind `except Exception`) findings in `fundamentals_ingest.py` and the orchestrator: those
handlers used to re-raise in release mode, which kept ruff quiet; they now always log and skip,
which is what the normal path always did. Left as is.

**Not done here:** `infrastructure/capture_mode.py` (`strict_release` capture mode,
`WAREHOUSE_RELEASE_MODE`) is a separate concept documented in `docs/capture-modes.md`; whether it
has any live caller after this change is unchecked (the Standards review found no consumer of
`resolve_capture_mode` outside its own module, so it may be dead too).
