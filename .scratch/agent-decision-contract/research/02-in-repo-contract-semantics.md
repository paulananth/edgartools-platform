# In-repo Decision Contract semantics versus SQL sketches

Ticket: `.scratch/agent-decision-contract/issues/02-inventory-in-repo-contract-semantics.md`

Scope: in-repo Python serving modules, SQL sketches, and matching tests. No
live Snowflake. Canonical semantics today live in the Python modules (they
are unit-tested); the SQL files are projections/sketches that disagree with
that Python in several load-bearing places. The map already labels this
head as "not agent-grade."

Primary sources:

- `edgar_warehouse/serving/decision_contract.py`
- `edgar_warehouse/serving/watermark_aggregator.py`
- `edgar_warehouse/serving/subject_feature_screen.py`
- `edgar_warehouse/serving/subject_bundle_read.py`
- `edgar_warehouse/serving/dashboard_modes.py`
- `edgar_warehouse/serving/dashboard_query_registry.py`
- `infra/snowflake/sql/decision_contract/01_subject_feature_screen.sql`
- `infra/snowflake/sql/decision_contract/02_subject_bundle_read_issuer.sql`
- `infra/snowflake/sql/decision_contract/03_dashboard_contract.sql`
- `tests/unit/test_decision_contract.py`
- `tests/unit/test_subject_feature_screen.py`
- `tests/unit/test_subject_bundle_read.py`
- `tests/unit/test_dashboard_modes.py`
- `tests/serving/test_watermark_aggregator.py`
- `tests/architecture/test_dashboard_decision_contract.py`

---

## 1. How `evaluate_agent_grade` decides aligned vs not

Symbol: `evaluate_agent_grade` in
`edgar_warehouse/serving/decision_contract.py`.

It is fail-closed. It builds a `DecisionWatermark` via
`build_decision_watermark` (missing keys become empty string / false), then
appends a reason for every broken rule. `agent_grade = len(reasons) == 0`.
The watermark is always attached for audit (`watermark=wm if agent_grade or
True else wm`).

Rules actually checked (docstring + body, locked by
`tests/unit/test_decision_contract.py`):

| Rule | Fail reason |
| --- | --- |
| `business_date` non-empty | `missing business_date` |
| `gold_run_id` non-empty | `missing gold_run_id` |
| `graph_generation_id` non-empty | `missing graph_generation_id` |
| `silver_completeness_ok` is True | `silver_completeness_ok is false` |
| `graph_parity_ok` is True | `graph_parity_ok is false (verify-graph / parity required)` |
| `high_severity_reconcile_open` implies `reconcile_waived` | `open high-severity reconcile findings (not waived)` |
| `bronze_persist_used` iff `bronze_content_hashes` non-empty | either `bronze_persist_used but bronze_content_hashes empty` or `bronze_content_hashes present without bronze_persist_used` |

`REQUIRED_COMPONENTS` lists only the five identity/completeness fields. It
is not iterated; bronze and reconcile are extra, not in that tuple.

There is no "aligned" boolean on `AgentGradeResult`. Alignment is a
separate concept on the aggregator:

- `watermark_aggregator.reconcile_cause_reference` sets
  `CauseAlignment.aligned = stuck_stage is None`, where `_stuck_stage`
  walks `STAGE_ORDER = ("silver", "mdm", "gold", "graph")` and returns the
  first incomplete stage. Graph completeness is stored as
  `graph_parity_ok`.
- `rollup_business_date` then calls `evaluate_agent_grade` with:
  - empty date → all flags false / ids empty → not agent-grade
  - otherwise `silver_completeness_ok = all(row.aligned)`
  - `gold_run_id` / `graph_generation_id` filled only when **every** cause
    on that date is aligned **and** those ids are a singleton set;
    otherwise they are `""` (which itself fails agent-grade)
  - `graph_parity_ok = all_aligned and all(row.graph_parity_ok)`

Daily agent-grade therefore requires every `cause_reference` on the date
aligned, a unique gold run id, a unique graph generation id, and graph
parity on every row. Bronze hashes and reconcile are **not** supplied by
the rollup, so they default false/empty and do not block unless a caller
passes them. Test:
`tests/serving/test_watermark_aggregator.py::test_daily_rollup_is_not_agent_grade_until_every_cause_on_the_date_aligns`.

SQL does **not** call `evaluate_agent_grade`. `03_dashboard_contract.sql`
fail-closes `DECISION_CONTRACT_STATUS` on a publication row:

- `PUBLICATION_STATUS = 'ready'`
- `ALIGNMENT_STATUS = 'aligned'`
- `COVERAGE_STATE IN ('complete', 'partial')`
- join `NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER` where
  `POINTER_ID = 'active'` and `ACTIVE_GENERATION_ID = p.GRAPH_GENERATION_ID`
- `QUALIFY ROW_NUMBER() ... = 1` (newest `BUSINESS_DATE`, then
  `PUBLISHED_AT`)

That is a different gate: operator-asserted publication + live pointer
match, not the Python reason list. No SQL column exists for
`silver_completeness_ok`, `graph_parity_ok`, bronze hashes, or reconcile
waiver. `docs/dashboard-decision-contract.md` describes the publication
insert as a manual operator assertion after full-chain + `mdm reconcile`.

Python screen/bundle still emit rows when `agent_grade` is false (audit).
SQL 03 agent-ready views return zero rows when the publication gate fails.
SQL 03 display views (`DECISION_CONTRACT_DISPLAY_STATUS`,
`SUBJECT_BUNDLE_DISPLAY_ISSUER`) still return rows with
`READINESS_STATE = 'not_ready'`.

---

## 2. Watermark fields Python emits versus SQL columns

### Python `DecisionWatermark` (`decision_contract.py`)

Always present on `evaluate_agent_grade(...).watermark`:

| Field | Required for agent-grade |
| --- | --- |
| `business_date` | yes |
| `gold_run_id` | yes |
| `graph_generation_id` | yes |
| `silver_completeness_ok` | yes (must be True) |
| `graph_parity_ok` | yes (must be True) |
| `decision_contract_version` | no (defaults `"1"`) |
| `bronze_content_hashes` | only if `bronze_persist_used` |
| `bronze_persist_used` | inverse of hashes |
| `high_severity_reconcile_open` | blocks unless waived |
| `reconcile_waived` | only with open high-severity |
| `notes` | no |

Screen and bundle identity subsets (`_watermark_identity` in
`subject_feature_screen.py` and `subject_bundle_read.py`) project only
`business_date`, `gold_run_id`, `graph_generation_id`,
`decision_contract_version`.

Aggregator `CauseAlignment` adds `cause_reference`, `silver_complete`,
`mdm_complete`, `gold_complete`, `aligned`, `stuck_stage`,
`first_seen_at`, `aligned_at`. Those never become SQL contract columns.

CLI `edgar-warehouse reconcile-decision-watermark`
(`edgar_warehouse/cli.py::_handle_reconcile_decision_watermark`) is
observe-only: it writes a JSON alignment store and prints the rollup; it
does not INSERT `DECISION_CONTRACT_PUBLICATION`.

### SQL `DECISION_CONTRACT_PUBLICATION` (`03_dashboard_contract.sql`)

| Column | Python counterpart |
| --- | --- |
| `DECISION_WATERMARK` STRING PK | none — Python never concatenates a single watermark string |
| `DECISION_CONTRACT_VERSION` | `decision_contract_version` |
| `BUSINESS_DATE` DATE | `business_date` (Python is `str`) |
| `GOLD_UPDATED_AT` TIMESTAMP_TZ | **not** `gold_run_id` — different identity |
| `GRAPH_GENERATION_ID` | `graph_generation_id` |
| `COVERAGE_STATE` | none |
| `ALIGNMENT_STATUS` | loosely `CauseAlignment.aligned`, not `agent_grade` |
| `PUBLICATION_STATUS` | none |
| `PUBLISHED_AT` / `PUBLISHED_BY` | none |

`DECISION_CONTRACT_STATUS` adds `GRAPH_ACTIVATED_AT` from the pointer.

`SUBJECT_FEATURE_SCREEN` (`01_subject_feature_screen.sql`) emits only
`'1' AS decision_contract_version`. No `business_date`, `gold_run_id`,
`graph_generation_id`, completeness flags, bronze, or reconcile columns.
Ticket 10's "results carry Decision Watermark identity" is true in Python
(`build_subject_feature_screen`) and false in the SQL view.

`SUBJECT_BUNDLE_READ_ISSUER` in 03 attaches publication identity
(`DECISION_WATERMARK`, `BUSINESS_DATE`, `GOLD_UPDATED_AT`,
`GRAPH_GENERATION_ID`, `GRAPH_ACTIVATED_AT`, `COVERAGE_STATE`,
`ALIGNMENT_STATUS`) plus feature-screen columns. Still no `gold_run_id`,
bronze hashes, silver completeness, graph parity, or reconcile fields.

Allowlist name `DECISION_WATERMARK` in `dashboard_modes.AGENT_VIEW_ALLOWED_OBJECTS`
has no SQL object — it is a publication **column**, not a view.

---

## 3. Feature-screen universe versus Ticket 14 warehouse-active ∩ MDM-active

Ticket 14 (closed predecessor): Decision Subject Universe is warehouse
active ∩ MDM active. Python implements that intersection. SQL 01 does not.

### Python (matches Ticket 14)

`decision_subject_universe(warehouse_active_ciks, mdm_active_ciks)` in
`subject_feature_screen.py` is `sorted(set(warehouse) & set(mdm))`.
`build_subject_feature_screen` lists **every** intersection CIK even when
`period_rows` have no features (`fy_features_coverage = unavailable`).
Callers inject both sets; the module does not query a table.

Locked by `tests/unit/test_subject_feature_screen.py::UniverseTests` and
`test_screen_lists_only_universe_members`.

### SQL 01 (MDM-active only)

`01_subject_feature_screen.sql` universe CTE:

```sql
SELECT DISTINCT cik::NUMBER AS cik
FROM {{ database }}.EDGARTOOLS_GOLD.MDM_COMPANY_ENTITY
WHERE cik IS NOT NULL
  AND LOWER(COALESCE(tracking_status, '')) = 'active'
```

Header comment is explicit: "Decision Subject Universe is
MDM_COMPANY_ENTITY (tracking_status='active'), not warehouse COMPANY.
Ticket 41: the previous COMPANY self-join treated every gold company as
MDM-active." `tests/serving/test_watermark_aggregator.py` and
`tests/architecture/test_dashboard_decision_contract.py` only assert
`MDM_COMPANY_ENTITY` + `tracking_status='active'`; they do **not** assert
an intersection.

### SQL 03 bundle (MDM tracking on warehouse COMPANY ∩ graph ∩ screen)

`SUBJECT_BUNDLE_READ_ISSUER` filters
`EDGARTOOLS_GOLD.COMPANY` with
`LOWER(COALESCE(c.TRACKING_STATUS, '')) = 'active'`, joins active-generation
company nodes in `MDM_GRAPH_NODES`, and joins `SUBJECT_FEATURE_SCREEN`.

`COMPANY.tracking_status` is **not** warehouse seed/sync tracking. Gold
`company.sql` left-joins `source("mdm_export", "MDM_COMPANY_ENTITY")` and
selects `m.tracking_status`. Warehouse-only CIKs have NULL tracking_status
and drop out of the `'active'` filter. So 03 is MDM-active companies that
also exist in silver `sec_company` **and** in the active graph generation
**and** on the feature screen — still not Ticket 14's warehouse-active
predicate.

Warehouse-active in the live platform is Bookkeeping Postgres
`sec_company_sync_state.tracking_status` via
`BookkeepingStore.get_tracked_ciks` (`edgar_warehouse/bookkeeping/store.py`).
No decision-contract SQL reads that table.

Explore `dashboard_workflows.fundamentals.screen` uses
`coalesce(c.tracking_status, 'active') = 'active'`, treating missing MDM
status as active — the opposite of SQL 03's empty-string coalesce.

Related open grilling ticket:
`.scratch/agent-decision-contract/issues/04-define-warehouse-active-universe-predicate.md`.

### Other screen disagreements (not universe, but same view)

- Python `PURE_SEC_FEATURE_KEYS` is 19 keys (incl. `ebitda`,
  `eps_diluted`, `ebitda_margin`, `roe`, `roa`). Gold
  `FINANCIAL_FACTORS` has no `ebitda` / `eps_diluted` / `ebitda_margin`;
  it names `return_on_equity` / `return_on_assets` / `operating_margin`.
  SQL 01 projects a **subset** and aliases `return_on_equity AS fy_roe`.
- Coverage: Python `present` if **any** of the 19 keys is non-null; SQL FY
  `empty` if revenue, net_income, **and** total_assets are all null (ignores
  FCF/ROE); SQL interim `empty` if revenue and net_income are both null.
- No-FY interim: Python still picks latest interim; SQL 01 `interim` is
  `INNER JOIN fy`, so no FY ⇒ no interim (`not_applicable`).
- FY period token: Python accepts `FY`/`fy`/`annual`/`YEAR`; SQL is
  `UPPER(fiscal_period) = 'FY'` only.
- Tie-break: SQL `QUALIFY ... period_end DESC, accession_number DESC`;
  Python `_latest_by_period_end` uses only `period_end` string max.

---

## 4. Issuer bundle sections Python can build versus SQL views

Python `build_issuer_subject_bundle`
(`edgar_warehouse/serving/subject_bundle_read.py`) always returns these
section keys when the subject is in-universe:

| Section constant | Agent-grade rule in Python | SQL object |
| --- | --- | --- |
| `insiders` | graph `IS_INSIDER` **and** gold ownership accession; gold-only strings are `non_agent_grade` | none |
| `employment` | `EMPLOYED_BY` with `proxy_def14a` or `item_5_02`; gold proxy pay sidecar | none |
| `holders_of_subject` | 13F holders + Latest Complete Holdings Period lag | `BUNDLE_HOLDERS_OF_SUBJECT` (02 sketch only) |
| `subject_as_manager_portfolio` | issuer's own 13F book, separate name | none |
| `auditor` | prefer PCAOB id (`prefer_auditor_evidence_pcaob_id`) | `BUNDLE_AUDITOR` (02 sketch only) |
| `has_parent` | only if `parent_inventory_complete`; else unavailable | none |
| `subject_features` | same FY/interim as-of as ticket 10 | columns on `SUBJECT_FEATURE_SCREEN` / 03 bundle, not a section object |
| `adv` | always `not_applicable` / `pure_issuer_bundle_does_not_require_adv` | none (02 comment: no ADV view required) |

Out-of-universe (`subject_in_decision_universe=False`) returns
`agent_grade=False`, extra reason `subject not in Decision Subject
Universe`, and `sections={}`.

### SQL 02 sketches (not wired into 03, not granted)

`BUNDLE_HOLDERS_OF_SUBJECT` reads
`EDGARTOOLS_GOLD.INSTITUTIONAL_HOLDINGS` (`issuer_cik`, `manager_cik`,
`cusip`, `shares`, `period_of_report`, `lag_days`). No
`subject_as_manager_portfolio` dual.

`BUNDLE_AUDITOR` reads **`EDGARTOOLS_SOURCE.SEC_AUDITOR_REPORT_EVIDENCE`**
(`registrant_cik`, `principal_firm_name`, `pcaob_firm_id`), not GOLD.
`tests/serving/test_watermark_aggregator.py::test_bundle_auditor_reads_source_auditor_evidence_not_gold`
locks SOURCE and forbids
`EDGARTOOLS_GOLD.SEC_AUDITOR_REPORT_EVIDENCE`. Claude.md still describes
the GOLD path as a sketch bug; the current file already uses SOURCE.
Python `_build_auditor_section` is source-agnostic (takes injected
`auditor_edges`).

02 is untemplated (`EDGARTOOLS_DECISION` with no `{{ database }}`) and
its own header says not to treat the views as agent-grade until
MDM/graph gold tables are wired. `docs/dashboard-decision-contract.md`
applies 01 + 03 only; 02 is not in that apply path.

### SQL 03 "bundle" is identity + features, not neighborhood

`SUBJECT_BUNDLE_READ_ISSUER` / `SUBJECT_BUNDLE_READ` are company identity
(CIK, entity, tickers, SIC, …) plus feature-screen FY/interim columns plus
publication watermark columns. No insiders, employment, 13F holders,
auditor, parent, or ADV sections. Display twin
`SUBJECT_BUNDLE_DISPLAY_ISSUER` is the same shape with
`READINESS_STATE`.

Reader grants in 03 (six SELECTs): `DECISION_CONTRACT_STATUS`,
`SUBJECT_BUNDLE_READ`, `SUBJECT_BUNDLE_READ_ISSUER`,
`DECISION_CONTRACT_DISPLAY_STATUS`, `SUBJECT_BUNDLE_DISPLAY_ISSUER`,
`DASHBOARD_SUBJECT_RESOLVER`. Not granted: `SUBJECT_FEATURE_SCREEN`,
`BUNDLE_HOLDERS_OF_SUBJECT`, `BUNDLE_AUDITOR`,
`DECISION_CONTRACT_PUBLICATION`, graph tables.

`AGENT_VIEW_ALLOWED_OBJECTS` also lists `SUBJECT_BUNDLE_READ_MANAGER`
(Python `manager_bundle_read.build_manager_subject_bundle` exists; no SQL
view — out of this map's destination) and the 02 sketch names
`BUNDLE_HOLDERS_OF_SUBJECT` / `BUNDLE_AUDITOR`.

---

## 5. How Agent View vs Explore is encoded in Python

Fully encoded in Python. SQL has no mode column.

`edgar_warehouse/serving/dashboard_modes.py` (ticket 13 / ADR 0001):

- Modes: `MODE_AGENT_VIEW = "agent_view"`, `MODE_EXPLORE = "explore"`.
- `normalize_mode`: unknown/empty **defaults to agent_view** (fail-closed
  to contract-only).
- Sticky session keys `SESSION_MODE_KEY`, `SESSION_CIK_KEY`.
- Agent View allowlist `AGENT_VIEW_ALLOWED_OBJECTS` (bare object names).
  `is_object_allowed` / `assert_query_allowed` raise `PermissionError` for
  free gold (`FINANCIAL_FACTORS`, `EDGARTOOLS_GOLD.COMPANY`, …).
- Explore: every object allowed, but `EXPLORE_BANNER` is labeled
  **Not** the agent Decision Contract and **not** Trading Decision input.
- `dual_mode_cik_context` supports same-CIK audit comparison.

`dashboard_query_registry.AGENT_VIEW_QUERIES` is the closed-world Agent
View SQL (three queries, `max_rows <= 25`, no `EDGARTOOLS_GOLD.` /
`NEO4J_GRAPH_MIGRATION.` in the SQL text):

| Query id | Object |
| --- | --- |
| `agent.contract_status` | `DECISION_CONTRACT_DISPLAY_STATUS` |
| `agent.subject_search` | `DASHBOARD_SUBJECT_RESOLVER` |
| `agent.subject_bundle` | `SUBJECT_BUNDLE_DISPLAY_ISSUER` |

Those are the **display** views, not the fail-closed
`DECISION_CONTRACT_STATUS` / `SUBJECT_BUNDLE_READ_ISSUER`. Agent View can
therefore show `READINESS_STATE = 'not_ready'` /
`NOT_READY_REASON = 'no_verified_publication'` instead of an empty
result. `DASHBOARD_SUBJECT_RESOLVER` is deliberately not
readiness-gated (gold `COMPANY` + `TICKER_REFERENCE`, no
`TRACKING_STATUS` filter).

SiS `infra/snowflake/streamlit/streamlit_app.py` imports these helpers
(or the staged flat `dashboard_modes.py` copy). Agent View company page
calls `_render_agent_view_company` and returns before Explore gold
charts. Explore-only surfaces (`FINANCIAL_FACTORS`, ERDP explore
products) are gated with `_is_object_allowed`. Tests:
`tests/unit/test_dashboard_modes.py`,
`tests/architecture/test_dashboard_decision_contract.py`,
`tests/architecture/test_snowflake_streamlit_financial_factors.py`.

SQL 03 encodes ready vs not-ready display, not Agent View vs Explore.

---

## Disagreement summary (Python canonical vs SQL)

| Concern | Python (unit-tested) | SQL sketches |
| --- | --- | --- |
| Agent-grade | `evaluate_agent_grade` reason list | Publication READY + ALIGNED + coverage + live graph pointer |
| Watermark identity | Composite fields incl. `gold_run_id`, bronze, reconcile | String `DECISION_WATERMARK` + `GOLD_UPDATED_AT`; no bronze/reconcile/`gold_run_id` |
| Feature-screen watermark | Identity dict on every payload | Hardcoded version `'1'` only |
| Universe | warehouse-active ∩ MDM-active (injected sets) | MDM_COMPANY_ENTITY `tracking_status='active'` (01); COMPANY MDM tracking ∩ graph ∩ screen (03) |
| Bundle sections | 8 neighborhood sections | 02: holders + SOURCE auditor only; 03: identity + features, no neighborhood |
| Auditor table | Injected edges | `EDGARTOOLS_SOURCE.SEC_AUDITOR_REPORT_EVIDENCE` (not GOLD) |
| Agent View vs Explore | First-class Python mode + allowlist + banners | Absent; 03 only ready/not-ready display |
| Fail-closed rows | Rows still returned, `agent_grade=false` | Ready views empty; display views labeled `not_ready` |

Canonical in-repo behavior for this ticket is the Python serving layer.
SQL 01/02/03 are sketches/projections that a later implementation ticket
must reconcile with Ticket 14 universe, ADR 0006 bronze identity, and the
issuer neighborhood sections Python already names.
