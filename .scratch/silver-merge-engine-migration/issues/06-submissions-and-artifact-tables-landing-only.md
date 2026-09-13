# 06 — Make the submissions/artifact-path tables landing-only

**Type:** task (likely splits once started — this is the largest remaining set)

## Question

Everything left in `silver_store.py` after Tickets 02–05: `merge_company`, `merge_addresses`,
`merge_former_names`, `merge_submission_files`, `merge_filings`, `merge_current_filing_feed`,
`replace_company_tickers`, `upsert_raw_object`, `merge_filing_attachments`, `upsert_filing_text`,
the ownership trio, the ADV five, `merge_subsidiary_evidence`, `merge_auditor_report_evidence`,
`merge_pcaob_firm_identities`. These are `daily_incremental`/`load_history`'s own write path
(`_execute_warehouse_bronze_capture`), so unlike 02–05 this touches the scheduled pipeline.

**Before switching any of them, the exhaustive-reader grep Ticket 01 learned the hard way:**
`warehouse_orchestrator.py:4688` (`parse-ownership-bronze` reads `sec_company_filing` locally —
wired into the deploy script, a live no-op today since the table is always empty),
`reference_catalog_silver_acceptance.py` (three local reads, the same read-back-verify shape
Ticket 02 deleted), `mdm/adv_bulk.py` (which reader is `silver` there?), and the five
`drive-*-discovery` drivers (they call these writers; they are NOT to be deleted — the
change-propagation map owns their future, see the map's Notes).

**Notes from Ticket 04's GoF review (2026-09-13), for whoever picks this up:**

- None of this ticket's tables has `ingested_at`; they stamp `last_sync_run_id` (and company,
  filings and tickers also `last_synced_at = now`). That stamp depends on `sync_run_id`, so it
  is a method taking an argument (e.g. `_sync_run_stamp(sync_run_id)`), not a staticmethod;
  `merge_company`'s `first_sync_run_id` fallback goes in per-call `defaults`. The helper's
  signature needn't change.
- None of these writers' `values_fn`s replace a present value (no `bool()`/`or ""`), so no
  call-site coercion comprehensions are expected.
- `merge_filing_attachments` and `merge_current_filing_feed` reject any *falsy* required value,
  including `""`; the helper's NOT NULL check only rejects `None`. Decide parity (call-site
  pre-check vs. a stricter helper check) explicitly, don't lose it silently.

**Done:** as Ticket 04, per table or per group; a live `daily_incremental` run showing landing
rows for every table in the group.

**Blocked by:** [Ticket 04](04-per-filing-tables-landing-only.md).

## Reader inventory and split (2026-09-13)

Unlike Tickets 02–05, several of these tables are **written and read back inside the same run**
(local DuckDB is never *hydrated*, but it is *written* during a run). The discriminating
question per reader: is the row it reads written by this same run, or by an earlier one?
Earlier-run reads can move to the Snowflake reader. Same-run reads cannot: landing rows are not
queryable as silver until the dbt collapse runs.

Every dbt silver model below partitions on exactly the old `ON CONFLICT` key.

### 06a — ADV, relationship-source evidence and current filing feed (no same-run readers)

`merge_adv_filings`, `merge_adv_offices`, `merge_adv_disclosure_events`,
`merge_adv_private_funds`, `merge_adv_firm_roster`, `merge_subsidiary_evidence`,
`merge_auditor_report_evidence`, `merge_pcaob_firm_identities`, `merge_current_filing_feed`.

- Readers outside `silver_store.py` are MDM (`pipeline.py`, `coverage.py`,
  `mdm_entity_backfill.py`), all on the Snowflake reader.
- One local reader: `_run_parse_adv_bronze`'s `already_parsed` gate reads `sec_adv_filing`
  once, at the start of the standalone `parse-adv-bronze` command. Local DuckDB is fresh
  there, so the read is always empty today. The in-run set is maintained in Python
  (`already_parsed.add`), so going landing-only changes nothing.
- The callers (`adv_bulk_ingest`, `adv_firm_roster_ingest`, `auditor_evidence`,
  `subsidiary_exhibits`, the orchestrator's PCAOB and ADV branches) never read back.
- **Stamp:** `last_sync_run_id` from `sync_run_id` (plus `last_synced_at` on the feed).
  Today `@track_landing_rows` lands raw rows without either.
- **Parity to decide:** several old `values_fn` lookups are `row["key"]` on **nullable**
  columns (firm roster counts, subsidiary/auditor evidence fields). An absent key raised
  `KeyError`; the NOT NULL-only helper would accept it. `merge_current_filing_feed` silently
  **skips** rows with a falsy `accession_number` (it does not raise).

### 06b — company submissions group (no production same-run readers)

`merge_company`, `merge_addresses`, `merge_former_names`, `merge_submission_files`, all called
from `stage_submission`.

- `get_company`/`get_addresses` are only read in tests, plus
  `submissions_silver_acceptance.py:353`. That is a read-back-verify in the dormant
  `drive-submissions-discovery` driver, the same shape Ticket 02 settled as VERIFIED on
  record.
- `stage_submission` DELETEs `sec_company_former_name`/`sec_company_submission_file` per CIK
  before re-merging. That replace semantics never reached landing (pre-existing, not
  introduced).
- `silver_support/session.reset_submission_state` (same DELETEs) has no callers.
- `merge_company`'s `first_sync_run_id` fallback goes into per-call `defaults`.

### 06c — ownership trio

`merge_ownership_reporting_owners`, `merge_ownership_non_derivative_txns`,
`merge_ownership_derivative_txns`.

- `parse-ownership-bronze`'s `already_parsed` read has the same shape as ADV's (empty today).
- `relationship_bulk_load.insider_inventory` runs from MDM (Snowflake).
- **Open:** `silver_once.has_successful_ownership_parse`'s fallback reads
  `sec_ownership_reporting_owner` on the local `db` inside the artifact pipeline. The primary
  check is the bookkeeping `sec_parse_run`, but the fallback can only see same-run rows.
  Decide whether it goes, or moves to the Snowflake reader.

### 06d — the same-run core (blocked on a decision, not a mechanical switch)

`merge_filings`, `upsert_raw_object`, `merge_filing_attachments`, `upsert_filing_text`,
`replace_company_tickers`.

- **Blocker:** `warehouse_orchestrator.py` release/recurring candidate seeding calls
  `merge_filings`, then `db.get_filing` for each required accession, and fails closed with
  "could not be staged". Landing-only `merge_filings` would make every `daily_incremental`
  with required daily-index candidates raise.
- `bronze_filing_artifacts.fetch_filing_artifacts` gates idempotency and bronze-recovery on
  `get_filing`/`get_filing_attachments`/`get_raw_object` rows written earlier in the same
  run.
- The orchestrator's ownership-skip release evidence (sha256 via `get_raw_object`),
  `capture_parity.py` (`SELECT * FROM sec_raw_object` right after fetching) and
  `targeted_resync` (`get_filing`) all read same-run rows.
- `reference_catalog_silver_acceptance.py` reads `sec_company_ticker` right after
  `replace_company_tickers`.
- `fundamentals_ingest`, `filing_text_sweep` and `silver_once.get_ciks_with_new_qualifying_filing`
  already read Snowflake (`source=` / `fetch_with_query_id`). Not blockers.
- **Needs a grilling:** keep a per-run in-memory working set that these readers consult;
  keep the local DuckDB write for these tables only; or move the reads to bookkeeping.
  This decides whether Ticket 09 (drop `duckdb`) is reachable.

Order: 06a first (no reader touched), then 06b, then 06c. 06d waits on its decision.

## 06a Answer

Resolved 2026-09-13 in code; live verification still owed.

- The nine 06a writers call `_record_landing_passthrough` with a new `_sync_run_stamp(sync_run_id)`
  (the feed adds `last_synced_at`). Their `@track_landing_rows` decorators, `_merge_rows` /
  `_merge_rows_bulk` SQL and `values_fn` lambdas are gone. DuckDB DDL kept.
- **Parity decisions:**
  - Absent key on a nullable column (old `row["key"]` → `KeyError`) is now accepted. Every
    production caller builds complete rows: dataclass `asdict` for subsidiary, auditor and
    PCAOB; full dict literals for firm roster and ADV bulk. NOT NULL columns still raise.
  - `merge_current_filing_feed` still skips (does not raise on) a falsy `accession_number`,
    filtered at the call site.
  - Old absent-key defaults kept: subsidiary `immediate_parent_known=False` and
    `parser_version="subsidiary_exhibit_v1"`; auditor `parser_version="auditor_evidence_v1"`.
- **Collapse keys verified:** all nine dbt silver models partition on the old `ON CONFLICT` key.
  Columns the old `DO UPDATE SET` never touched (first-insert-wins in DuckDB, last-seen in dbt):
  - none on the four ADV tables, the firm roster or the feed (the ADV bulk two-pass upsert
    also resolves to last-seen for every column);
  - `sec_subsidiary_evidence`: `registrant_cik`, `document_type`;
  - `sec_auditor_report_evidence`: the non-updated columns that can really differ for one
    key are `form_type`, `document_name`, `audited_period_end`, `principal_firm_name`,
    `principal_firm_location`, `parser_version`;
  - `sec_pcaob_firm_identity`: `snapshot_uri`.

  Pre-existing (landing already got every raw write), not introduced here.
- **Unlike Tickets 04/05, the stamp fixes no live gap:** no MDM or dbt consumer filters these
  tables on `last_sync_run_id`, and `merge_current_filing_feed` has no production caller.
  It is kept for parity with what the old DuckDB rows carried.
- **Reader-inventory correction:** `validate_data_quality` (ADV foreign-key checks) and
  `table_reconciliation` also read these tables, but from a hydrated copy of the old canonical
  DuckDB, never same-run rows. Nothing breaks.
- Within one call, duplicate keys both land, and which one dbt keeps is not guaranteed
  (`parse_sequence` is assigned per load). Callers never send conflicting duplicates
  (`adv_bulk_ingest` rejects them), and this was already true before.
- `get_current_filing_feed` deleted: no callers, and it could only ever return `None` now.
- Tests: `test_adv_and_evidence_landing_passthrough.py` (landing-only + stamp override, the
  feed's `last_synced_at` and skip, duplicates passed through, defaults, NOT NULL raising, a
  20k-row private-fund batch making at most one DuckDB call). `test_merge_adv_bulk.py`
  deleted (it tested the DuckDB upsert). The firm roster ingest, ADV bulk ingest, ADV
  acceptance and kind-dispatch tests now assert on landing rows; the sharding and
  schema-migration tests seed through `tests/support/silver_rows.py`; `CountingConnection`
  moved there.

**Still owed:**
- a live `ingest-relationship-sources` run (ADV bulk, firm roster, subsidiary, auditor,
  PCAOB) showing landing rows with `last_sync_run_id` populated;
- the pre-existing all-NULL-column `pa.Table.from_pylist` risk in `silver_landing_writer.py`
  has no landing-writer test (the deleted bulk test covered the DuckDB side only).
