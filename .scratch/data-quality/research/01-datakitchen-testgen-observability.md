# DataKitchen TestGen and Observability: what they are, and what to take

Research note, 2026-09-27, written on branch `claude/research-dataops-testgen`
and moved to main on 2026-10-02 (ticket 22 cites it).
No sec.gov request was made. GitHub, DataKitchen docs and one GLEIF page only.

## Answer first

- **TestGen** is a real data-quality tool. It profiles tables, then writes
  tests from what it saw. It has 51 test-type definitions in source (the docs
  say 47) and 32 "hygiene issue" types. It runs against PostgreSQL. It is
  Apache-2.0 and very active.
- **Observability** is a pipeline-status tool. Pipelines post events to it,
  and it raises alerts on late, missing or failed runs. It needs Kafka and
  MySQL. It overlaps Bookkeeping and the Change Journal.
- **Recommendation:** adopt neither as a platform piece. Borrow TestGen's
  best checks into the `checks:` and `gate:` sections the Source Contract
  spec already defines. Run them in production through one Bookkeeping check.
  Optionally run TestGen **once**, locally and offline, as a profiling probe on
  a copy of `mdm_v2` and silver, and turn real findings into checks.

Pinned sources used below:

- `TG` = https://github.com/DataKitchen/dataops-testgen/blob/98acd8ad37314abeacda65d7f10cf61b997f5c3a
  (cloned 2026-09-27; head commit 2026-09-19)
- `OB` = https://github.com/DataKitchen/dataops-observability/blob/83e38e1ebf5e76fc93400f676e4085005c4b0f31
  (cloned 2026-09-27; head commit 2026-09-23)
- Our repo paths are at worktree commit `265d8e97`.
- "(docs)" marks a claim taken from docs.datakitchen.io, not from source.

---

## 1. What each tool is and does

### 1.1 TestGen

**Purpose.** TestGen finds data issues by "data profiling, new dataset
screening and hygiene review, algorithmic generation of data quality
validation tests, ongoing production testing of new data refreshes, and
continuous anomaly monitoring" (`TG/README.md`).

**Profiling.** It runs one SQL query per database flavor that counts, per
column, values, nulls, distinct values, lengths, patterns, leading spaces,
quoted values, digits and dummy values
(`TG/testgen/template/flavors/postgresql/profiling/project_profiling_query.sql`,
lines 82-97). Results go to `profile_results` and `profiling_runs`
(`TG/testgen/template/dbsetup/030_initialize_new_schema_structure.sql`).

**Auto-generated tests.** Each test type carries a `selection_criteria`
expression over the profile. When a column's profile matches, TestGen writes
a test for it, with a baseline taken from the profile. Example: `Pattern_Match`
is generated when a column has one frequent pattern and more than 10 distinct
values; its baseline regex is built from that pattern
(`TG/testgen/template/dbsetup_test_types/test_types_Pattern_Match.yaml`,
`selection_criteria`, `default_parm_values`). Tests come in "generation sets"
(`Standard`, `Monitor`) (same file, `generation_sets`). CLI:
`testgen run-test-generation` (`TG/testgen/__main__.py`, line 282).

**Test types.** 51 YAML definitions in
`TG/testgen/template/dbsetup_test_types/`. Two are marked `active: N`
(`Valid_Characters`, `Valid_Month`), and one is `CUSTOM`. The docs say "47 test
types" in six dimensions: validity, consistency, completeness, timeliness,
accuracy, uniqueness (docs:
https://docs.datakitchen.io/testgen/what-is-testgen/). Each type declares
`run_type` (`CAT` = batched column/aggregate tests, `QUERY` = one query per
test, `METADATA`), `test_scope` (column, table, referential, custom,
tablegroup), `dq_dimension`, `default_severity` (Fail, Warning, Log), and one
SQL measure per flavor. The full list is in section 3.

**Hygiene issues ("anomalies").** 32 YAML definitions in
`TG/testgen/template/dbsetup_anomaly_types/`, matching the docs' "32 types of
hygiene issues" (docs). They are rules over the profile, not over the data.
Each has an `issue_likelihood` (Definite, Likely, Possible, Potential PII) and
a `suggested_action`. Example: `Non_Standard_Blanks` fires when a column holds
empty strings or dummy values
(`TG/testgen/template/dbsetup_anomaly_types/profile_anomaly_types_Non_Standard_Blanks.yaml`, `anomaly_criteria`).

**Scoring.** Each failed test or hygiene issue gets a *prevalence* (share of
rows affected) times a *risk factor*. A score is the record-weighted sum:
"Prevalence % * dq_score_risk_factor ... SUM(calculated prevalence * record
count) / SUM(record count)"
(`TG/testgen/template/rollup_scores/calc_prevalence_test_results.sql`, lines
1-7). The formula and factor live on each type
(`dq_score_prevalence_formula`, `dq_score_risk_factor`). Score cards roll up by
column, dimension and "impact dimension" (`TG/testgen/template/score_cards/`).

**Monitors.** Four monitor kinds: freshness, volume, schema, metric. They "use
prediction models to automatically calculate expected ranges based on
historical data" (docs). In source, thresholds come from a SARIMAX forecast
(`TG/testgen/commands/test_thresholds_prediction.py`, imports
`get_sarimax_forecast`; `statsmodels` and `holidays` in `TG/pyproject.toml`).

**Which databases.** The code knows ten flavors: `redshift`,
`redshift_spectrum`, `snowflake`, `mssql`, `postgresql`, `databricks`,
`bigquery`, `oracle`, `sap_hana`, `salesforce_data360`
(`TG/testgen/common/database/flavor/flavor_service.py`, line 12).
**PostgreSQL is supported.** Every test type has a `postgresql` SQL form,
either in `cat_test_conditions` (CAT types) or in `test_templates` (all 13
QUERY/METADATA types, e.g. `Dupe_Rows`, `Aggregate_Balance`, `CUSTOM`,
`Schema_Drift`). The docs also list MySQL, Azure Synapse and Fabric (docs), but
there is no `mysql` folder under `TG/testgen/template/flavors/`. Treat the docs
list as wider than the code.

**How tests run.** TestGen connects read-only to the target and runs SQL
there: "no data is extracted or copied" (docs). It stores only results and
bad-row lookups, run on demand (`target_data_lookups` in each YAML).

**CLI.** Click commands in `TG/testgen/__main__.py`: `run-profile` (line 267),
`run-test-generation` (282), `run-monitor-generation` (338), `run-tests`
(352), `run-monitors` (390), `get-profile-anomalies` (454), `list-tests`,
`list-test-runs`, `export-test-metadata` (874, writes test definitions to
YAML), `list-test-types` (887), `quick-start` (560), `standalone-setup` (632),
`run-app` (1047). There is also an MCP server and a FastAPI API
(`TG/pyproject.toml`: `mcp[cli]`, `fastapi`).

**UI.** A Streamlit app on port 8501 (`TG/docker-compose.yml`;
`streamlit==1.55.0` in `TG/pyproject.toml`).

**What it stores.** Everything lives in its own PostgreSQL metadata database
(default name `datakitchen`, schema `testgen`) (`TG/docs/configuration.md`,
`TG_METADATA_DB_NAME`, `TG_METADATA_DB_SCHEMA`). Tables include `connections`,
`table_groups`, `profiling_runs`, `profile_results`,
`profile_anomaly_results`, `test_suites`, `test_definitions`, `test_runs`,
`test_results`, `test_types`, `job_schedules`, `auth_users`
(`TG/testgen/template/dbsetup/030_initialize_new_schema_structure.sql`). Test
definitions are rows in that database, not files in a repo. It creates its own
roles, `testgen_execute` and `testgen_report` (`TG/docs/configuration.md`,
`DATABASE_EXECUTE_USER`, `DATABASE_REPORT_USER`).

**Link to Observability.** TestGen can push test results to Observability's
`test-outcomes` endpoint (`TG/testgen/commands/run_observability_exporter.py`,
lines 301-324).

### 1.2 Observability

**Purpose.** It "monitors every data journey from data source to customer
value ... so that problems are detected, localized, and understood
immediately" (`OB/README.md`).

**Journeys and components.** A *journey* is a DAG of *components* (batch
pipelines, datasets, servers, streaming pipelines). Edges are
`JourneyDagEdge(left, right)`, and a cycle is rejected
(`OB/common/entities/journey.py`).

**Events API.** Pipelines report by POSTing JSON to the Event API. v2 routes:
`/batch-pipeline-status`, `/dataset-operation`, `/message-log`,
`/metric-log`, `/test-outcomes` (`OB/event_api/routes/v2_routes.py`, lines
29-33). A test outcome has a name and a status `PASSED`, `FAILED` or `WARNING`
(`OB/common/events/v2/test_outcomes.py`, lines 47-50). Calls authenticate with
a project service-account key (`OB/common/auth/keys/service_key.py`). The API
puts each event on a Kafka topic (`OB/event_api/endpoints/v2/event_view.py`,
lines 10 and 32; topics in `OB/common/kafka/topic.py`). Agents can also scrape
tools and post for you (docs:
https://docs.datakitchen.io/observability/what-is-observability/).

**Alerts.** A run can raise `LATE_END`, `LATE_START`, `MISSING_RUN`,
`COMPLETED_WITH_WARNINGS`, `FAILED`, `UNEXPECTED_STATUS_CHANGE`. A journey
instance can raise `LATE_END`, `LATE_START`, `INCOMPLETE`, `OUT_OF_SEQUENCE`,
`DATASET_NOT_READY`, `TESTS_FAILED`, `TESTS_HAD_WARNINGS`
(`OB/common/entities/alert.py`, lines 26-48). Levels are `WARNING` and `ERROR`
(same file, line 19).

**Rules and actions.** A `Rule` belongs to a journey (optionally one
component), holds a condition (`rule_data`) and an action with arguments
(`OB/common/entities/rule.py`, lines 31-40). Actions are e-mail and webhook
(`OB/common/actions/send_email_action.py`, `webhook_action.py`). The docs call
this "trigger-condition-action" (docs). Services: `event_api`, `agent_api`,
`observability_api`, `run_manager`, `rules_engine`, `scheduler`, a UI
(`OB/` top-level folders).

---

## 2. Technical fit

| | TestGen | Observability |
|---|---|---|
| License | Apache-2.0 (`TG/LICENSE`; GitHub API `license.spdx_id`) | Apache-2.0 (`OB/LICENSE`) |
| Language | Python >=3.11 (`TG/pyproject.toml`) | Python 3.12+ (`OB/README.md`) |
| Runtime | Docker compose: `datakitchen/dataops-testgen:v2` plus `postgres:14.1-alpine` (`TG/docker-compose.yml`); or pip with `standalone-setup`, which starts an embedded PostgreSQL from the `pixeltable-pgserver` extra (`TG/testgen/__main__.py` line 632; `TG/pyproject.toml` `[standalone]`); Helm charts in `TG/deploy/charts` | Docker compose with `apache/kafka:3.9.1`, `mysql:8.4`, backend and UI images (`OB/deploy/docker-compose/compose.yaml`, lines 14, 46, 63, 96); or minikube plus Helm (`OB/README.md`) |
| Metadata store | Its own PostgreSQL | MySQL (`PyMySQL`, `peewee` in `OB/pyproject.toml`) |
| Dependencies | Heavy: drivers for Databricks, Snowflake, BigQuery, Oracle, SAP HANA, Salesforce, MSSQL; pandas, numpy, scipy, statsmodels, Streamlit, FastAPI, MCP (`TG/pyproject.toml`) | Flask, gunicorn, confluent-kafka, peewee, APScheduler (`OB/pyproject.toml`) |
| Fully local | Yes (standalone or compose) | Yes (compose), but needs Kafka and MySQL |
| Offline | Works, but calls out by default: Mixpanel analytics is on unless `TG_ANALYTICS=no` (`TG/testgen/settings.py`, lines 498-510); a latest-version check fetches an S3 JSON with a 3 s timeout and has no off switch, only `pypi`/`docker` modes (`TG/testgen/common/version_service.py`, lines 12 and 64; `settings.py` line 437). Streamlit's own usage stats are turned off (`--browser.gatherUsageStats=false`, `TG/testgen/__main__.py`, line 1025) | No telemetry found by grep (`mixpanel`, `telemetry`, `analytics`, `gtag`, `segment`, `googletagmanager`) of the backend services and `observability_ui`; outbound only for webhook and e-mail actions |
| Maturity | Created 2024-04-17; 79 stars, 7 forks, 10 contributors; 776 commits since 2026-03-27; latest release 5.92.2 on 2026-09-19; classifier "Production/Stable" (GitHub API; `TG/pyproject.toml`) | Created 2024-04-17; 55 stars, 3 forks, 7 contributors; 22 commits since 2026-03-27; latest release 2.12.5 on 2026-07-24 (GitHub API) |

Counts from `gh api repos/DataKitchen/<repo>`, `/releases`, `/contributors`,
and `/commits?since=2026-03-27` (paginated), run 2026-09-27.

---

## 3. The catalog, and what applies to our data

### 3.1 How our data is shaped (the facts that decide fit)

- **SEC company** records reach MDM through `sec.submissions.company.v1`:
  `cik`, `entity_name`, `sic`, `state_of_incorporation`, `fiscal_year_end`,
  `business_address.*` (`rules/sources/sec.submissions.company/source.yaml`).
- **SEC state codes are not US-only.** SEC writes codes like `E9`, `X1` and
  `XX` ("unknown"); the full list is `rules/reference/sec-place-codes.yaml`
  (header comment).
- **Tickers belong to Security, not Company** (`skills/rules/SKILL.md`, line
  50). Ticker checks go with the Security kind or the ticker catalog, not
  `mdm_v2.company`.
- **GLEIF Level 1** fields: LEI, legal name, legal address, jurisdiction,
  legal form, entity status, registration status, dates, managing LOU,
  validation source (`rules/sources/gleif/source.yaml`). Relationships:
  `IS_DIRECTLY_CONSOLIDATED_BY` and `IS_ULTIMATELY_CONSOLIDATED_BY`, keyed by
  start, end and type (same file).
- **GLEIF enumerations** (LEI-CDF 3.1): RegistrationStatus `PENDING_VALIDATION`,
  `ISSUED`, `DUPLICATE`, `LAPSED`, `MERGED`, `RETIRED`, `ANNULLED`,
  `CANCELLED`, `TRANSFERRED`, `PENDING_TRANSFER`, `PENDING_ARCHIVAL`;
  EntityStatus `ACTIVE`, `INACTIVE`, `NULL`; EntityCategory `BRANCH`,
  `GENERAL`, `FUND`, `SOLE_PROPRIETOR`, `RESIDENT_GOVERNMENT_ENTITY`,
  `INTERNATIONAL_ORGANIZATION`; ValidationSources `PENDING`,
  `ENTITY_SUPPLIED_ONLY`, `PARTIALLY_CORROBORATED`, `FULLY_CORROBORATED`
  (https://www.gleif.org/en/about-lei/common-data-file-format/current-versions/level-1-data-lei-cdf-3-1-format).
- **CIK and LEI formats are already enforced** at the adapter. `_sec_cik`
  rejects non-digits, more than 10 digits and zero; `_lei` checks the
  20-character shape and mod 97 == 1 (`edgar_warehouse/mdm/clean/adapters.py`,
  lines 36-59). A bad one becomes a rejected record, not a silent pass.
- **`mdm_v2.company` is versioned.** Each row has `valid_from`/`valid_to`;
  the current row has `valid_to IS NULL`
  (`edgar_warehouse/mdm/migrations/037_clean_mdm_company_versions.sql`, lines
  4-52). Any uniqueness check must filter to current rows, or history rows
  fail it. TestGen supports this through a per-test `{SUBSET_CONDITION}`
  (e.g. `TG/testgen/template/dbsetup_test_types/test_types_Dupe_Rows.yaml`).
- **Two current accepted companies may share a CIK or LEI on purpose.** The
  indexes are not unique: "An identifier can already appear on two separately
  reviewed identities. Preserve that conflict for the Merge Stage to
  adjudicate" (same migration, comment above `company_current_cik`). So a
  duplicate count is a *metric to watch*, not a failure.
- **Several columns are `jsonb`** (`address`, `identifiers`, `fields`, `body`),
  and every `gleif_*` date is `text` (same migration). TestGen profiles
  columns, not keys inside jsonb, so it will not see address parts. It will
  not run its date tests on text dates; it will raise
  `Char_Column_Date_Values` instead.

### 3.2 Test types (51 in source)

"Use" says where the idea applies to us. **Yes** = worth borrowing now.
**Later** = useful once we keep history. **No** = does not fit.

| Test type (source name) | What it checks | Use for us |
|---|---|---|
| `Required` | No nulls | **Yes.** SEC `cik`, `entity_name`; GLEIF `lei`, legal name, registration status; relationship start/end; `mdm_v2.company.status`. Our `not_null` already does this. |
| `Unique` | Every value distinct | **Yes.** Silver keys: SEC `cik`, GLEIF `lei`, relationship (start, end, type). On `mdm_v2.company` only as a metric on current rows (see 3.1). Our `unique` already does this. |
| `Unique_Pct` | Share of distinct values stable | Later |
| `Dupe_Rows` | No duplicate rows over chosen columns | **Yes**, as `unique` over the record key. |
| `Pattern_Match` | Values match one regex | **Yes.** CIK `^\d{10}$` in silver; LEI shape. Our `pattern` already does this. |
| `LOV_Match` | Every value in an allowed list | **Yes.** GLEIF statuses, category, validation source; SEC `state_of_incorporation` against `sec-place-codes.yaml`; `mdm_v2.company.status`. Our `in_set`. |
| `LOV_All` | Every listed value appears | Later (e.g. both GLEIF relationship types present in a full file) |
| `US_State` | Two-letter US state | **No.** Its list is US-only (`TG/testgen/template/dbsetup_test_types/test_types_US_State.yaml`, line 49). SEC uses `E9`, `X1`, `XX`. Use `in_set` against our reference file. |
| `Valid_US_Zip`, `Valid_US_Zip3` | US ZIP shape | Partly: SEC business postcode when country is US. Needs a condition. |
| `Street_Addr_Pattern` | Enough values look like street addresses | No (global addresses) |
| `Email_Format` | E-mail shape | No |
| `Alpha_Trunc` | Max length not shrinking | Later (catches truncated names) |
| `Constant` | Column is one constant | No |
| `Condition_Flag` | A SQL condition holds per row | **Yes**, as a custom check, e.g. relationship start != end. |
| `CUSTOM` | Any SQL rule | **Yes**, same as our `custom_check`. |
| `Combo_Match` | Values or combos exist in a reference table | **Yes.** GLEIF relationship `end` exists as a Level 1 LEI; `mdm_v2.company_alias.canonical_id` has a current company row. |
| `Aggregate_Balance`, `_Percent`, `_Range`, `Aggregate_Minimum` | Group totals match a reference | Partly: silver row count vs MDM accepted + deferred + rejected count (this is Bookkeeping's `work.accounting` idea). |
| `Distribution_Shift` | Value distribution vs reference | Later |
| `Row_Ct` | Row count at or above a floor | **Yes.** Our `row_count`. |
| `Row_Ct_Pct`, `Volume_Trend` | Row count within a band of the last run | **Yes, later.** A GLEIF Golden Copy that shrinks sharply is suspect. Needs the previous publication's count. |
| `Table_Freshness`, `Freshness_Trend`, `Recency` | Data updated recently | **Yes**, on publication time (GLEIF Golden Copy is published "three times daily", `docs/research/gleif-open-data-augmentation-2026-09-11.md`, line 44; SEC capture is per run). Better at the Bookkeeping level than per column. |
| `Future_Date`, `Future_Date_1Y` | No dates in the future | **Yes.** GLEIF `LastUpdateDate`, `InitialRegistrationDate`, `EntityCreationDate`. `NextRenewalDate` is legitimately future. |
| `Min_Date` | Dates after a floor | Partly: a floor on GLEIF registration dates. The floor value needs an operator decision. |
| `Daily_Record_Ct`, `Weekly_Rec_Ct`, `Monthly_Rec_Ct`, `Distinct_Date_Ct` | Every period has rows | No (not transactional) |
| `Missing_Pct` | Share of nulls stable | **Later.** Watch fill rate of `state_of_incorporation`, `sic`, postcode. |
| `Distinct_Value_Ct` | Distinct count not dropping | Later |
| `Avg_Shift`, `Incr_Avg_Shift`, `Outlier_Pct_Above/Below`, `Variability_Increase/Decrease`, `Min_Val`, `Dec_Trunc`, `Metric_Trend` | Numeric measures | No (no measures in company data) |
| `Timeframe_Combo_Gain`, `Timeframe_Combo_Match` | Latest period keeps prior combos | Later: "no LEI vanished between Golden Copies" - but GLEIF semantics say absence never retires (`rules/sources/gleif/source.yaml`, `semantics`), so a report, not a gate. |
| `Schema_Drift` | Table columns changed | Covered by the contract's `schema_version` and the reader's strict validation |
| `Valid_Characters` (inactive), `Valid_Month` (inactive) | Invalid characters; month format | See hygiene below |

Source: one YAML per type in `TG/testgen/template/dbsetup_test_types/`
(fields `test_name_long`, `run_type`, `test_scope`, `dq_dimension`,
`default_severity`, `active`).

### 3.3 Hygiene issue types (32 in source)

| Hygiene type | What it flags | Use for us |
|---|---|---|
| `Non_Standard_Blanks` | Empty strings and dummy values (`n/a`, `null`, `none`, `unknown`, runs of `0`, `9`, `x`, `z`, dashes, `?`) | **Yes, first.** Our rules skill already logs "placeholder values the source writes for 'none' (`000000000`, the text `NULL`, a code such as `8888`)" as a gap the contract cannot express (`skills/rules/SKILL.md`, line 111). TestGen's list (`TG/testgen/template/flavors/postgresql/profiling/project_profiling_query.sql`, lines 88-97) catches `000000000` and `NULL` but not `8888`, so ours must take a per-column list. |
| `Leading_Spaces` | Leading spaces | **Yes.** Names, address lines, codes. |
| `Non_Printing_Chars` | Control or zero-width characters | **Yes.** Names from XML/JSON sources. |
| `Quoted_Values` | Values wrapped in quotes | **Yes**, cheap. |
| `Inconsistent_Casing` | Mixed upper and title case in one column | Report only. Name matching goes through the Name Census and its normalizers (`rules/merge/kinds/company.yaml`, `name_census_match@1`), not raw casing. |
| `Non_Alpha_Name_Address`, `Non_Alpha_Prefixed_Name` | Names with no letters, or starting with a symbol | **Yes.** A company name with no letters is a defect. |
| `Char_Column_Date_Values` | Text column holding dates | Expected for `gleif_*` dates; the answer is typing them, not a check. |
| `Char_Column_Number_Values`, `Small_Numeric_Value_Ct`, `Char_Column_Number_Units` | Text column holding numbers | Expected for `cik`, `sic`; ignore. |
| `Column_Pattern_Mismatch`, `Table_Pattern_Mismatch` | Mixed patterns in one column | Probe only (useful for postcodes). |
| `Invalid_Zip_USA`, `Invalid_Zip3_USA` | Bad US ZIP | Partly (US rows only). |
| `Unexpected_US_States`, `Unexpected_Emails`, `Potential_PII` | Content in the wrong column; PII | PII matters for Person later, not Company. |
| `Potential_Duplicates` | Mostly unique column with a few repeats | **Yes, as a metric.** Repeated CIK or LEI on current `mdm_v2.company` rows. |
| `Standardized_Value_Matches` | Values equal after trim/case | Probe: names that differ only by case/space. |
| `Variant_Coded_Values` | Same meaning coded several ways | Probe: status columns. |
| `Boolean_Value_Mismatch`, `Delimited_Data_Embedded`, `Multiple_Types_*`, `No_Values`, `Small_Divergent_Value_Ct`, `Small_Missing_Value_Ct`, `Suggested_Type`, `Unlikely_Date_Values`, `Recency_One_Year`, `Recency_Six_Months` | General hygiene | Probe only. `Unlikely_Date_Values` helps once dates are typed. |

Source: one YAML per type in `TG/testgen/template/dbsetup_anomaly_types/`
(fields `anomaly_name`, `anomaly_criteria`, `issue_likelihood`).

---

## 4. Options, cost and benefit

### What we already have (this changes the options)

- The Source Contract spec **already defines** a `checks:` list with built-ins
  `not_null`, `unique`, `in_set`, `pattern`, `row_count` and `custom_check`.
  Each returns violations with the row key, never a bare true or false
  (`docs/specs/source-contract/spec.md`, §14, line 651).
- It **already defines** a Batch Gate: limits default to zero, and any looser
  limit needs a `why:` (same spec, §16, line 749).
- The spec's production section, `source run`, **does not mention** running
  `checks` or the `gate` on production batches (same spec, §18, line 826).
  Checks run in Named Cases and in the Proving Run's Batch Gate (§14, last
  paragraph). The spec's status is **proposed** (line 3).
- Bookkeeping **already has** a named check registry. A target lists check
  names in `source.yaml` (e.g. `checks: [manifest.hash, work.accounting,
  journal.delivered, mdm.publication]` in `rules/sources/gleif/source.yaml`),
  and code registers functions by name
  (`edgar_warehouse/bookkeeping/clean/config.py`, `Registry.check`, line 60;
  existing checks in `capabilities.py`, lines 72-76, and
  `mdm_capabilities.py`, line 127).

So "add a `quality` section" is not needed. The section exists as `checks:`
and `gate:`.

### Option A: adopt TestGen as a tool

- **Benefit:** 51 test types and 32 hygiene rules for free. Profiling finds
  issues nobody thought to write. A UI with scores and drill-down. Postgres is
  supported.
- **Cost:**
  - A second system with its own Postgres metadata database, roles
    (`testgen_execute`, `testgen_report`), users and scheduler. If pointed at
    the MDM Postgres itself, those roles land there.
  - Test definitions live in its database, not in reviewed rules files. This
    splits "what is checked" away from the Rules Database and PR review.
  - Generated baselines come from the data being tested, so they bake in
    today's defects as "normal".
  - It cannot look inside `jsonb`, and our dates are text.
  - Heavy dependency set (many cloud drivers, Streamlit, statsmodels).
  - Outbound calls by default (Mixpanel; version check with no off switch).
  - Its test results are not joined to our run ids or batches, and do not
    block anything.
- **Verdict:** no, as a platform piece. It is a second rules store, and
  that goes against lean/KISS.

### Option B: adopt Observability

- **Benefit:** a dashboard of runs and late/missing-run alerts across tools.
- **Cost:** Kafka, MySQL and several services to run. It duplicates what
  Bookkeeping (worklists, leases, checkpoints, verified completion) and the
  Change Journal already record. Every pipeline would need an extra event
  client. Less active project (22 commits in six months).
- **Verdict:** no. Borrow only its alert names (`LATE_START`, `LATE_END`,
  `MISSING_RUN`, `TESTS_FAILED`, `TESTS_HAD_WARNINGS`, `DATASET_NOT_READY`) as
  plain words for Bookkeeping run outcomes.

### Option C: borrow TestGen's ideas into our rules files (recommended)

- **Benefit:** checks live in the Source Contract, are versioned and approved
  with it, run in the Proving Run and on every production batch, and block
  verified completion. One system. Violations carry row keys.
- **Cost:** a spec change (a few new built-ins, and §18 running the gate),
  small engine code, and one Bookkeeping check function. The spec is Codex's
  to build (`docs/specs/source-contract/spec.md`, line 7), so the change goes
  through that handover.

### Option D: run TestGen once as a probe (optional, cheap)

- Install with pip and `standalone-setup` in a scratch folder. Set
  `TG_ANALYTICS=no`. Point it at a **local copy** of `mdm_v2` and one silver
  batch, never at production. Read the hygiene issues. Turn the real ones into
  checks. Then delete it.
- **Cost:** about half a day (my estimate, not measured). The version check will try the network and time
  out after 3 s.
- **Benefit:** finds unknown issues without adopting anything.

---

## 5. Recommendation

1. **Take option C, plus option D once.**
2. **Where the checks run.** Keep `checks:` and `gate:` in the Source
   Contract. Amend spec §18 so `source run` evaluates the active version's
   `checks` against its `gate` limits on each production batch. Register one
   Bookkeeping check, e.g. `data.gate`, that passes only when every limit
   holds, and list it in the source's target `checks`. Keep violations as
   evidence beside the run, as other receipts are.
3. **Add few new built-ins, each borrowed from a TestGen type:**
   - `identifier_format: { table, column, format }`: reuses the one `FORMATS`
     table in `adapters.py` (`sec_cik`, `lei`), so the silver check and the
     adapter never disagree. (TestGen: `Pattern_Match`, but with the mod-97
     check TestGen lacks.)
   - `in_set` with `values_from: <rules/reference file>`: so SEC state codes
     check against `sec-place-codes.yaml`, not a copied list. (TestGen:
     `LOV_Match`.)
   - `no_placeholder: { table, column, values: [...] }`: dummy values per
     column. This closes the gap the rules skill logs. (TestGen:
     `Non_Standard_Blanks`.)
   - `clean_text: { table, column }`: no leading/trailing space, no
     non-printing characters, no wrapping quotes. (TestGen: `Leading_Spaces`,
     `Non_Printing_Chars`, `Quoted_Values`.)
   - `references: { table, column, to_table, to_column }`: every value exists
     in another table. (TestGen: `Combo_Match`.)
   - Later, `row_count_change: { table, max_drop_pct }` against the previous
     publication. (TestGen: `Row_Ct_Pct`, `Volume_Trend`.)
4. **MDM invariants** are not per-source. Put them in one Bookkeeping check on
   the MDM target (next to `mdm.publication`), run after each merge, over
   current rows only (`valid_to IS NULL`).

### First checks to add

SEC company silver (`sec.submissions.company`):

1. `not_null` and `unique` on `cik`.
2. `identifier_format` on `cik` with `sec_cik`.
3. `in_set` on `state_of_incorporation`, `values_from:
   rules/reference/sec-place-codes.yaml` (nulls allowed).
4. `clean_text` on `entity_name` and the business address parts.
5. `no_placeholder` on `state_of_incorporation`, `sic` and the business
   postcode, with the values the profile finds.

GLEIF (`gleif`). Column names below follow the spec's worked GLEIF example,
table `gleif_lei_record` (`docs/specs/source-contract/spec.md`, lines
905-955). GLEIF's real silver column names are not fixed yet (the live
source is read by `gleif_source.py`, and `rules/sources/gleif/source.yaml` has
no `silver` section), so treat the names as placeholders.

6. The spec example **already has** `not_null`, `unique` and `pattern` on
   `lei` (lines 952-955). The only new piece is `identifier_format: lei`, so
   the mod-97 check runs at silver too.
7. `in_set` on `registration_status`, `entity_status`, `entity_category`
   (and validation source, once it is a column) with the LEI-CDF 3.1 values
   above. Note: the spec example allows only `[ACTIVE, INACTIVE]` for
   `entity_status` (line 955), but LEI-CDF 3.1 also allows `NULL`. Settle
   this before the check runs on real files.
8. Addresses: `clean_text` on `legal_address_line1`, `legal_address_more`,
   `legal_city`. `pattern` `^[A-Z]{2}$` on `legal_country` and `hq_country`.
   For `legal_jurisdiction`, LEI-CDF 3.1 says it "SHALL either be a
   2-character country code conforming to ISO 3166-1 alpha-2 or a region code
   conforming to ISO 3166-2" (GLEIF page above), so `pattern`
   `^[A-Z]{2}(-[A-Z0-9]{1,3})?$`. The page I read does not state the format of
   the address `Country` and `Region` fields, so confirm the 2-letter
   country rule on a profile before making it a zero-limit gate.
9. Relationships: `unique` on (start, end, type); `identifier_format: lei` on
   start and end; `custom_check` start != end; `references` from end to the
   Level 1 LEI (limit with a `why:`, since a parent may be outside the file's
   scope).
9b. `Future_Date` idea as a `custom_check`: `last_update` and
   `initial_registration` not after the publication date.

`mdm_v2` (one MDM check, current rows):

10. Count current accepted companies sharing a `cik`, and sharing an `lei`.
    Report both; gate with a non-zero limit and a `why:`, because the design
    keeps such conflicts for the Merge Stage.
11. Every non-null `cik` and `lei` on current rows passes its format.
12. Every `company_alias.canonical_id` has a current company row.
13. Share of rows with `status = 'review'` or `quarantined`, as metrics.

Only `company` and `company_alias` get data checks here. The other `mdm_v2`
tables (`batch`, `checkpoint`, `publication`, `assertion`, `decision`,
`deferred_record` and so on) are control or evidence tables, already covered
by Bookkeeping's checks (`work.accounting`, `journal.delivered`,
`mdm.publication`).

Tickers: add their checks with the Security kind, not here.

## 6. Open questions for the operator

- Should production batches block on the gate (fail closed), or only report
  at first? The spec's defaults (limit zero) imply block.
- Is a sharp drop in a GLEIF Golden Copy's row count a blocker, and at what
  percentage?
- Where do the limits for the MDM checks (10-13) live? Source checks keep
  theirs in the contract's `gate:`. If MDM limits go in the kind or policy
  file, a change alters the policy digest and needs operator approval.
- Which dummy values does each SEC column really carry? Option D, or the rules
  skill's profile step, should answer this before check 5 is written.
