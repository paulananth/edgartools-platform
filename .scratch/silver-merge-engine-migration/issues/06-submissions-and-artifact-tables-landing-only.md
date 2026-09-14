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

**Status:** decided 2026-09-13 by grilling and resolved in code the same day (see "06d Answer");
live verification still owed.
Narrowed to `sec_company_filing`, `sec_filing_attachment` and `sec_raw_object` — tickers and
filing text moved to 06e.

`merge_filings`, `upsert_raw_object`, `merge_filing_attachments`, `upsert_filing_text`,
`replace_company_tickers` (as originally scoped).

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

### 06e — tickers and filing text (no same-run readers)

**Status:** open. Split off 06d by its grilling (2026-09-13).

`replace_company_tickers`, `upsert_filing_text`. A straight landing-only switch, same shape as
06a–06c.

- No same-run production reader: `seed-universe` gates `replace_company_tickers` on the
  bookkeeping source checkpoint, and `sec_filing_text` is read only by the filing-text sweep,
  on the Snowflake reader. The dormant reference-catalog acceptance driver's
  `sec_company_ticker` read-back takes Ticket 02's "VERIFIED on record" shape.
- `replace_company_tickers`'s local `DELETE ... WHERE source_name` never reached landing; the
  dbt model already partitions on `(cik, ticker, source_name)` behind `silver_not_retired`, so
  a ticker dropping out of a snapshot belongs to the Silver Landing Retirement Record, not to
  this switch (pre-existing).
- Keep each writer's own input checks ahead of the landing call (06d Answer, Q9).
- Delete the uncalled `get_filing_text`, `get_all_filing_texts` and
  `SilverDatabase.get_company_tickers`.
- `sec_filing_text`'s dbt model partitions on `(accession_number, text_version)`, the old key.

Order: 06a first (no reader touched), then 06b, then 06c. 06d is decided and waits on
implementation; 06e can go in either order with it.

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

## 06b Answer

Resolved 2026-09-13 in code; live verification still owed.

- `merge_company`, `merge_addresses`, `merge_former_names`, `merge_submission_files` call
  `_record_landing_passthrough`. Stamps: company, address and submission file use a new
  `_synced_now_stamp(sync_run_id)` (`last_sync_run_id` + `last_synced_at`, which also replaced
  the current filing feed's inline copy); former names use `_sync_run_stamp` alone, since that
  table has no `last_synced_at`. `merge_company` keeps `first_sync_run_id` as an absent-key
  default of the call's `sync_run_id`. Every old `row["key"]` lookup is a NOT NULL column except
  `former_name` (nullable; the old `row["former_name"]` only required the key, and DuckDB took
  a `None` value). `stage_former_name_loader` always sets that key, so the only caller is
  unchanged — the same "callers build complete rows" decision as 06a.
- **`stage_submission`** no longer runs its two per-CIK DELETEs (`sec_company_former_name`,
  `sec_company_submission_file`): they only ever cleared local DuckDB, and those tables are
  now always empty there. The DELETEs never reached landing (`@track_landing_rows` recorded
  merge rows only), so a former name or submission file SEC later drops from a payload
  already stayed in silver before this change — pre-existing, not introduced. Retiring such
  rows belongs with the Silver Landing Retirement Record fog on the map. `stage_submission`
  now also returns `company_rows_written`.
- **Read-back deleted:** the dormant `drive-submissions-discovery` acceptance driver verified
  its company producer with `get_company(cik)`; it now settles VERIFIED when
  `stage_submission` recorded a company row (an individual filer records none and still
  FAILS). Its `get_filing` half stays until 06d.
- **Dead code deleted:** `get_company`, `get_addresses`, `get_former_names`,
  `get_submission_files`, `session.reset_submission_state`, and `get_company_identity_ciks`
  (its Snowflake replacement `_company_identity_ciks_snowflake` has been the production path
  since Cutover Ticket 05; the local version could only ever return an empty set now).
- **Collapse keys verified:** the four dbt silver models partition on `cik`,
  `(cik, address_type)`, `(cik, ordinal)`, `(cik, file_name)` — the old `ON CONFLICT` keys.
  The only column the old `DO UPDATE SET` never touched is `sec_company.first_sync_run_id`
  (first-insert-wins in DuckDB, last-seen in dbt; the default makes it the latest run's id
  on every re-stage). Pre-existing.
- The stamps fix no live gap: nothing downstream filters these tables on
  `last_sync_run_id`/`last_synced_at`/`first_sync_run_id`.
- Tests: `test_company_submission_landing_passthrough.py` (landing-only + stamp override,
  `last_synced_at` present or absent per table, the `first_sync_run_id` default, NOT NULL
  raising). The entity-type gate, submissions acceptance and company-identity tests assert on
  landing rows (the last one reads back the Parquet the command flushes); the discovery
  command test drops its company read-back (that driver opens no landing export). The
  identity-window test of the deleted reader is replaced by
  `test_company_identity_ciks_snowflake_eligibility_sql_against_real_silver_schema`, which
  runs the Snowflake replacement's SQL against a real seeded DuckDB (the operating-or-
  ticker boundary was otherwise only mocked). The three passthrough test files share
  `tests/support/silver_rows.open_landing_db`.

**Still owed:** a live `daily_incremental` run showing `SEC_COMPANY`/`SEC_COMPANY_ADDRESS`/
`SEC_COMPANY_FORMER_NAME`/`SEC_COMPANY_SUBMISSION_FILE` landing rows with `last_sync_run_id`
populated.

## 06c Answer

Resolved 2026-09-13 in code; live verification still owed.

- `merge_ownership_reporting_owners`, `merge_ownership_non_derivative_txns` and
  `merge_ownership_derivative_txns` call `_record_landing_passthrough` with
  `_sync_run_stamp(sync_run_id)` and no defaults. The old `values_fn`s read only the key
  columns as `row["..."]` (`accession_number`, `owner_index`, `txn_index`), which are the
  primary-key columns the passthrough's NOT NULL check requires; every other column was
  `row.get(...)` with no default. So parity is exact: a missing key still raises, an absent
  nullable column still lands as NULL.
- **Duplicates within one call cannot happen:** `parsers/ownership.py` assigns `owner_index`
  and `txn_index` with `enumerate` per accession, so the dbt collapse's unordered
  within-load tiebreak never has two rows to pick between.
- **The open question — `has_successful_ownership_parse`'s fallback — is deleted, not moved.**
  The fallback read local `sec_ownership_reporting_owner` for "silver populated before
  parse_run was consistently written". That is a cross-run concern, and the primary check
  already answers it on durable state: `sec_parse_run` lives in the bookkeeping Postgres
  store and is committed after publish. The fallback was redundant by construction; after
  this ticket the local table is always empty anyway. Same-run is also covered: `_run_parse_pipeline`
  stages its parse run with `start_parse_run` (`session.add`) and the bookkeeping session
  autoflushes, so a later check in the same run sees it. The function no longer takes `db`.
  Moving the fallback to the Snowflake reader was rejected: it would add one Snowflake query
  per candidate accession and would restore skips that do not happen today.
- **One direction of behaviour change, noted:** an accession whose ownership rows landed but
  whose ADV merges in the same `_run_parse_pipeline` call then raised has its parse run marked
  `failed`. Before, a later run's fallback could have skipped it (only if the local rows were
  visible, which they no longer were); now it is re-parsed. Strictly the safer direction.
- **Pre-existing, not introduced:** `parse-ownership-bronze`'s `already_parsed` read has been
  permanently empty since local DuckDB stopped being hydrated, so that command has no
  cross-run skip. Its CLI help text claimed it did; corrected. Same shape as 06a's ADV note.
- **Reader inventory:** MDM (`pipeline.py`, `coverage.py`, `mdm_entity_backfill.py`,
  `relationship_bulk_load.insider_inventory` via MDM) reads on the Snowflake reader. The trio is
  also referenced by `validate_data_quality.py` (hydrated canonical copy),
  `table_reconciliation/contracts.py` and `case_coverage.py`, `migrate_silver_shards.py`,
  `sharded_reader.py` and `mdm/silver_parity.py` — none reads rows written earlier in the same
  run, so none is a blocker (the same correction 06a's Answer made).
- **Pre-existing, not introduced:** the same accession parsed twice in one load (`--force`, or
  `parse-ownership-bronze` and the artifact pipeline both landing it) gives the dbt collapse two
  rows with the same `parse_sequence` and no ordered tiebreak. `@track_landing_rows` had the
  same shape; both copies come from the same parser version and bronze bytes.
- `tests/application/test_parse_ownership_bronze.py` still exercises the `already_parsed` skip
  through a fake db that returns owner rows; that skip only fires within a run now.
- Tests: `test_ownership_landing_passthrough.py` (landing-only + stamp override, empty input,
  key columns raising, absent nullable columns not filled, no per-row DuckDB I/O; red first,
  then green). `test_silver_once.py`: `test_ownership_fallback_to_owner_rows` deleted — it
  covered the removed behaviour — while `test_ownership_parse_run_hit` still covers the
  surviving skip path, and a blank-accession case was added. The company-identity test's
  "no ownership rows" assertion on local DuckDB would have passed vacuously; it now asserts
  no ownership, ADV or 13F landing Parquet was written.

**Still owed:** a live `daily_incremental` run showing `SEC_OWNERSHIP_REPORTING_OWNER`/
`SEC_OWNERSHIP_NON_DERIVATIVE_TXN`/`SEC_OWNERSHIP_DERIVATIVE_TXN` landing rows with
`last_sync_run_id` populated.

## 06d Answer

Decided 2026-09-13 by grilling; implementation open. Recorded as
[ADR 0011](../../../docs/adr/0011-same-run-silver-reads-from-recorded-rows.md).

- **Scope narrowed (Q1):** 06d is `sec_company_filing`, `sec_filing_attachment` and
  `sec_raw_object`. `replace_company_tickers` and `upsert_filing_text` have no same-run
  production reader and move to 06e as a straight landing-only switch.
- **Same-run reads (Q2):** answered by an in-run lookup, not local DuckDB (would keep `duckdb`
  in the daily write path, so Ticket 09 unreachable), not the bookkeeping Postgres store
  (source content in a tracking-state store, commits only after publish, a round trip per
  lookup in the artifact loop), not the Snowflake reader (cannot see this run's rows before the
  landing load and dbt collapse). The readers it serves: `daily_incremental` candidate seeding
  (`merge_filings` then `get_filing`, fail-closed), configured-form selection,
  `fetch_filing_artifacts`, `_read_primary_artifact_bytes`, the ownership-skip and release
  evidence, and text extraction. The landing buffer is written out once at the end of the run,
  so the lookup can index the same row dicts it already holds.
- **Values when a key recurs in one run (Q4):** keep the old upsert's per-column rule. Columns
  its `DO UPDATE SET` never touched keep their first value in the run — for filings `cik`,
  `items`, `act`, `file_number`, `film_number`; for raw objects `fetched_at` — and every other
  column takes the latest write. Keys: filings by `accession_number`, attachments by
  `(accession_number, document_name)`, raw objects by `raw_object_id`. Reason: a multi-CIK
  accession staged twice (issuer, then reporting owner) must keep resolving
  `fetch_filing_artifacts` to the same bronze path.
- **Where it lives (Q5):** inside `SilverDatabase`, filled by the same writer call that records
  to landing; `get_filing`, `get_filing_attachments` and `get_raw_object` keep their
  signatures and read from it, so no caller changes. Ticket 09 moves it with the writers into
  the store-free module.
- **Without a landing buffer (Q6):** the lookup is filled anyway. The five dormant `drive-*`
  drivers open `SilverDatabase` without one and read back what they just wrote.
- **Writer input checks (Q9):** kept at each writer, ahead of the landing call —
  `merge_filing_attachments` still raises on a falsy `accession_number`/`document_name`/
  `document_type`/`document_url`, `upsert_raw_object` on its six named `None` fields — not
  replaced by the landing NOT NULL check alone.
- **Uncalled readers (Q10):** `get_raw_objects_for_accession`, `get_filings_for_cik` and
  `get_filing_count` have no callers and are deleted with 06d (06e deletes the filing-text and
  ticker ones), rather than being backed by the lookup.
- **Reads meant for earlier runs (Q3):** unchanged. The artifact cache hit (`existing_rows`)
  and a `--force` repair's prior hash/version snapshot have been empty since local DuckDB
  stopped being hydrated; the S3 LIST (Ticket 88 and the bronze-recovery fix) is what prevents
  re-fetching. `targeted-resync --scope accession` appears to fail outright for the same
  reason — [Ticket 10](10-restore-targeted-resync-accession-scope.md) verifies it live and
  picks a fix.
- **Is DuckDB gone after 06d/06e?** No. Every silver writer is DuckDB-free then, but DuckDB
  still backs the two fundamentals markers (bootstrap-fundamentals-crash-resume map), the
  landing NOT NULL lookup (`_required_columns` reads the DuckDB DDL; Ticket 09), the dead local
  readers (Ticket 07), the sharded reader and parity tooling (Ticket 08), the publish merge,
  shard migration, event reducer, historical backfill and scripts (Ticket 09), and the old
  canonical S3 files (duckdb-retirement-cutover Ticket 21). Ticket 09 stays reachable.

**Owed at implementation:** the 06a–06c build shape (passthrough, `/gof-refactor-reviewer`
first, red-first tests, 3-axis review), plus tests that a recurring key keeps first-value
columns, that the lookup works with no landing buffer, and that `daily_incremental`'s
candidate seeding still passes and still fails closed for a seed row missing its key; then a
live `daily_incremental` run showing the three tables' landing rows.

### 06d implementation (resolved 2026-09-13 in code; live verification still owed)

- **Writers:** `merge_filings`, `merge_filing_attachments` and `upsert_raw_object` call
  `_record_landing_passthrough`; their `@track_landing_*` decorators, the DuckDB upsert SQL,
  `_merge_rows` and `_merge_rows_bulk` are gone. Stamps: filings `_synced_now_stamp`,
  attachments `_sync_run_stamp`, raw objects none. Attachments keep the absent-key
  `is_primary=False` default.
- **Input checks (Q9):** attachments still raise on a falsy key/type/URL, raw objects on their
  six `None` fields. Filings add an explicit `"cik" not in row` check: `cik` is nullable, so the
  NOT NULL check alone would accept a row the old `row["cik"]` rejected. A missing
  `accession_number` is caught by the NOT NULL check. Every writer now validates all rows
  before recording any; the old attachment loop had already inserted earlier rows when a later
  one raised (the safer direction).
- **In-run lookup (Q2/Q4–Q6):** a module-level `_IN_RUN_LOOKUP_TABLES` names each table's key
  columns and first-value columns; the passthrough indexes recorded rows for those tables
  (`_remember_in_run`), with or without a landing buffer. `get_filing`, `get_filing_attachments`
  and `get_raw_object` keep their signatures and return copies carrying every DDL column in
  order (`None` where absent), the shape `SELECT *` returned. Values come back as written: the
  old DuckDB coercion (e.g. `DATE`) is gone, and no production caller relied on it (extractors
  and relationship candidates already pass `date`; `_ownership_filing_date`,
  `latest_filing_date` and `fundamentals_ingest` accept either).
- **Deleted (Q10):** `get_filing_count`, `get_filings_for_cik`, `get_raw_objects_for_accession`
  (and two test stubs that still modelled the last one).
- **`/gof-refactor-reviewer` (pre-code and post-diff):** leave the shape. The three tables differ
  only in data, so a spec dict plus two helpers beats three copies of the rule; the membership
  check in the passthrough is one branch at one site; `SilverDatabase` stays the owner until
  Ticket 09, which now notes that the lookup's column order comes from the DuckDB DDL.
- **Raw-SQL same-run readers (not in the grilling's inventory):**
  - `capture_parity.run_dual_path_filing_artifact_parity` read `SELECT * FROM sec_raw_object`
    after the legacy capture; it now reads attachments and raw objects through the lookup.
    `tests/acquisition/test_capture_parity_legacy_snapshot.py` covers it (red on the old read).
  - Release-mode Branch B (`bootstrap-batch --release-mode`) passes the local store as `source`
    to the fundamentals per-filing and 13F ingest, whose raw SQL now finds nothing, so it fails
    closed with "required candidates missing from filing manifest". Newly broken, dormant (the
    last two `one_click_data_refresh` executions ran `release_mode: false`); recorded in
    ADR 0011 and [Ticket 11](11-restore-release-mode-branch-b-same-run-reads.md). Its tests use
    hand-rolled `fetch()` stubs, which is why none caught it.
  - `parse-ownership-bronze` / `parse-adv-bronze` raw-SQL reads of `sec_company_filing` were
    already empty (nothing earlier in those commands fills the local store); pre-existing.
- **Pre-existing, not introduced:** the lookup keeps `fetched_at` first for raw objects and keys
  filings on `accession_number` alone, while the dbt models take the latest write for every
  raw-object column and partition filings on `(accession_number, cik)`. The lookup copies the old
  upsert on purpose (Q4); the old passthrough docstring's "same first-insert/last-write
  semantics" claim was corrected.
- **Tests:** `test_filing_artifact_landing_passthrough.py` (landing-only + stamps, the
  first-value/latest-write rule within and across calls, full-column copies, no-buffer lookup,
  every input check raising before recording; it carries over the deleted
  `test_merge_filings_bulk.py`'s cases). `test_submission_phase_order.py` gained candidate
  seeding against a real `SilverDatabase`: passes, fails closed with `ValueError` for a seed row
  missing `accession_number`, and with "could not be staged" for a row keyed elsewhere. Seven
  tests that read these tables from local DuckDB now read the lookup or landing rows; the two
  `drive-*` end-to-end tests drop their second-database read-back (the driver opens no landing
  export; the run's own read-back still gates `PUBLISHED`). Full suite (excluding
  `tests/integration`): 3504 passed, 5 skipped. mypy and ruff: nothing beyond the findings HEAD
  already had.

**Still owed:** a live `daily_incremental` run showing `SEC_COMPANY_FILING`/
`SEC_FILING_ATTACHMENT`/`SEC_RAW_OBJECT` landing rows (filings and attachments with
`last_sync_run_id` populated), and Ticket 11.
