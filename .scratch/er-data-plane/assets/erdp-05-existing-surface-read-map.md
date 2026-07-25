# ERDP-05 — Existing-surface ER read map (draft)

**Status:** draft — documents **current** agent-facing surfaces only; not a build plan.  
**Blocked by:** ERDP-04 (coverage-matrix freeze) for final **Covered** product pointers; this draft is usable without matrix freeze.  
**Sources:** `docs/data-architecture.md`, `docs/subject-bundle-read.md`, `docs/subject-feature-screen.md`, `docs/decision-watermark.md`, `docs/neo4j.md`, `docs/product-questions-and-dashboards.md`, `docs/manager-bundle-read.md`, `edgar_warehouse/config/gold_schemas.yaml`, `edgar_warehouse/serving/subject_bundle_read.py`, dbt `infra/snowflake/dbt/edgartools_gold/`, `assets/er-edgartools-gap-analysis.md`, `assets/er-skills-io.md`.  
**Consumers:** financial-services equity-research skills / agents; `spec.md` § ERDP-05.

---

## 0. How to read this map

### 0.1 Surface layers (agent relevance)

| Layer | Schema / object | Agent role |
|-------|-----------------|------------|
| **Gold free tables** | Snowflake `EDGARTOOLS_GOLD.*` dynamic tables (and `EDGARTOOLS_SOURCE` mirrors) | Explore / research / model inputs; **not** automatically Agent-Grade |
| **Decision Contract** | Watermark + Subject Feature Screen + Subject Bundle (issuer/manager) | **Agent-Grade** when `evaluate_agent_grade` passes |
| **MDM** | Snowflake MDM mirror (`MDM_*`) + operational Postgres | Entity resolution, tracking status, relationship SoE |
| **Graph** | `GRAPH_NODES` / `GRAPH_EDGES` (Snowflake-hosted Neo4j Graph Analytics) | Neighborhood edges; parity-gated for Agent-Grade |
| **Bronze / silver** | S3 bronze, DuckDB silver | Operator / rebuild path — not primary ER agent read surface |

### 0.2 Naming note (SOURCE vs GOLD)

| Warehouse export / SOURCE | dbt gold dynamic table (preferred agent SQL) |
|---------------------------|-----------------------------------------------|
| `COMPANY` | `EDGARTOOLS_GOLD.COMPANY` |
| `TICKER_REFERENCE` | `EDGARTOOLS_GOLD.TICKER_REFERENCE` |
| `FILING_ACTIVITY` | `EDGARTOOLS_GOLD.FILING_ACTIVITY` |
| `FILING_DETAIL` | `EDGARTOOLS_GOLD.FILING_DETAIL` |
| `OWNERSHIP_ACTIVITY` | `EDGARTOOLS_GOLD.OWNERSHIP_ACTIVITY` |
| `OWNERSHIP_HOLDINGS` | `EDGARTOOLS_GOLD.OWNERSHIP_HOLDINGS` |
| `SEC_FINANCIAL_FACT` | `EDGARTOOLS_GOLD.FINANCIAL_FACTS` |
| `SEC_FINANCIAL_DERIVED` | `EDGARTOOLS_GOLD.FINANCIAL_DERIVED` (+ YoY/TTM/peer ranks) |
| (derived) | `EDGARTOOLS_GOLD.FINANCIAL_FACTORS` (accounting-only factors / CAGRs) |
| `SEC_THIRTEENF_HOLDING` | `EDGARTOOLS_GOLD.INSTITUTIONAL_HOLDINGS` (+ QoQ / ranks) |
| `EARNINGS_RELEASE` | `EDGARTOOLS_GOLD.EARNINGS_RELEASES` |
| `EXECUTIVE_RECORD` | `EDGARTOOLS_GOLD.EXECUTIVE_RECORDS` (naming per dbt) |
| `ACCOUNTING_FLAG` | `EDGARTOOLS_GOLD.ACCOUNTING_FLAGS` |

Freshness status: `EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS` (from refresh status).

### 0.3 Decision Watermark (all Agent-Grade reads)

From `docs/decision-watermark.md` / `edgar_warehouse.serving.decision_contract`:

| Component | Role |
|-----------|------|
| `business_date` | As-of business date |
| `gold_run_id` | Gold / feature export identity |
| `graph_generation_id` | Hosted graph / relationship generation |
| `silver_completeness_ok` | Silver completeness claim for subject/window |
| `graph_parity_ok` | `mdm verify-graph` (or equivalent) passed |

**Fail closed** on missing identity, false completeness/parity, open high-severity reconcile (unless waived), or bronze-hash inconsistency. Agents **must abstain** when `agent_grade` is false.

### 0.4 Dual mode (human audit)

| Mode | Rule |
|------|------|
| **Agent View** | Decision Contract objects only |
| **Explore** | Free gold joins allowed; **labeled not-for-agent** |

---

## 1. COMPANY / TICKER_REFERENCE

### 1.1 COMPANY

| Field | Value |
|-------|--------|
| **Surface name** | `EDGARTOOLS_GOLD.COMPANY` (SOURCE: `COMPANY`; gold dim: `dim_company`) |
| **Grain** | One row per company (`company_key` / `cik`) — current company dimension |
| **Key columns** | `company_key`, `cik`, `entity_name`, `entity_type`, `sic`, `sic_description`, `state_of_incorporation`, `fiscal_year_end`, `last_sync_run_id` |
| **How to query (conceptual)** | Resolve identity by `cik` or join from `TICKER_REFERENCE.ticker` → `cik` → `COMPANY`. Universe counts / SIC slices: aggregate over `COMPANY`. Decision Subject Universe is **not** every COMPANY row — use warehouse active ∩ MDM active (Feature Screen). |
| **Freshness / watermark** | Built from silver `sec_company` via gold-refresh → Snowflake native pull → dbt DT (`TARGET_LAG = DOWNSTREAM`). Pin Agent-Grade work to Decision Watermark `gold_run_id` / `business_date`, not “latest table only.” Check `EDGARTOOLS_GOLD_STATUS` for lag. |
| **Limitations vs ER skills** | **Partial** for all 9 skills: gives CIK, name, SIC, FYE, entity type — not Street coverage book, not ratings, not exchange on this table (exchange lives on ticker ref). Does not replace firm “coverage universe” lists. Multi-ticker issuers need `TICKER_REFERENCE` fan-out. Parent hierarchy is MDM/graph (`HAS_PARENT_COMPANY`), not a COMPANY column pack. |

### 1.2 TICKER_REFERENCE

| Field | Value |
|-------|--------|
| **Surface name** | `EDGARTOOLS_GOLD.TICKER_REFERENCE` |
| **Grain** | One row per `(cik, ticker)` reference (schema PK focus: `cik` + `ticker`; exchange optional) |
| **Key columns** | `cik`, `ticker`, `exchange`, `last_sync_run_id` |
| **How to query** | Ticker → CIK: `WHERE UPPER(ticker) = ?`. CIK → tickers: all rows for cik. Seeded from SEC company tickers JSON (`seed-universe`). |
| **Freshness / watermark** | Same gold path as COMPANY; reference snapshot can lag daily trading symbol changes; not a real-time symbol master. |
| **Limitations vs ER skills** | **Partial** identity: no share class / primary flag productized beyond exchange; delisted/OTC completeness depends on SEC snapshot + tracking scope. Does not include market prices or mcap. |

**ER skill fit:** Identity bootstrap for all skills (initiation Task 1, idea screens, calendar universes) once ticker→CIK is resolved.

---

## 2. FINANCIAL_DERIVED / FINANCIAL_FACTS

### 2.1 FINANCIAL_FACTS (`SEC_FINANCIAL_FACT`)

| Field | Value |
|-------|--------|
| **Surface name** | `EDGARTOOLS_GOLD.FINANCIAL_FACTS` ← SOURCE `SEC_FINANCIAL_FACT` |
| **Grain** | One row per `(cik, accession_number, concept, fiscal_period, segment, period_end, period_start)` |
| **Key columns** | `cik`, `accession_number`, `concept`, `value`, `unit`, `decimals`, `fiscal_year`, `fiscal_period`, `period_start`, `period_end`, `form_type`, `segment`, `parser_version`, `ingested_at` |
| **How to query** | Filter `cik` + fiscal window; select `concept` (us-gaap tags); use `segment` for dimensional XBRL; use `period_start` to distinguish QTD vs YTD. Source: SEC companyfacts API → silver `sec_financial_fact` → export. |
| **Freshness / watermark** | Branch B entity-facts in `load_history` after Branch A. **Known gap:** raw companyfacts JSON is **not** bronze-persisted — reparse requires re-fetch from SEC. Gold lag follows gold-refresh + dbt. Agent as-of: prefer watermark-bound feature vectors (Subject Feature Screen) over ad-hoc latest facts for trading decisions. |
| **Limitations vs ER skills** | Strong for deep line-item digs (initiating-coverage model build). **Partial** for product/geo revenue models: `segment` string exists, no curated product-geo mart. Not a substitute for consensus or guidance. R&D/S&M headcount only if present as raw concepts. |

### 2.2 FINANCIAL_DERIVED (`SEC_FINANCIAL_DERIVED`)

| Field | Value |
|-------|--------|
| **Surface name** | `EDGARTOOLS_GOLD.FINANCIAL_DERIVED` ← SOURCE `SEC_FINANCIAL_DERIVED` |
| **Grain** | One row per `(cik, accession_number, fiscal_period, period_end)` (current + comparative rows possible per accession) |
| **Key columns** | Levels: `revenue`, `gross_profit`, `ebitda`, `ebit`, `net_income`, `eps_diluted`, balance sheet (`total_assets`…`shares_outstanding`), cash flow (`operating_cash_flow`, `capex`, `free_cash_flow`), margins, `roic`/`roe`/`roa`. Gold adds YoY growth, TTM metrics, SIC peer rank percentiles (see dbt model comments). |
| **How to query** | Prefer `is_current_period` (dbt-computed) or max `period_end` per `(cik, fiscal_period, fiscal_year)`. Multi-year model: filter FY / Q* and order by `period_end`. Join COMPANY for SIC peer context if using ranks. |
| **Freshness / watermark** | Computed from financial facts in silver; exported with fundamentals package. Subject Feature Screen / Bundle `subject_features` apply As-Of rules: **Primary FY + Latest Interim only if interim `period_end` > FY**. Null ≠ zero. |
| **Limitations vs ER skills** | Best platform fit for **model-update actuals** and **initiation Task 2** hist statements. **Partial** vs full ER model: no guidance values, no consensus, no market prices/PE/mcap (ADR 0001 pure-SEC). ROIC is simplified pre-tax (no NOPAT tax adjustment). CAGRs on `FINANCIAL_FACTORS` are FY-only with strict positivity guards. |

### 2.3 FINANCIAL_FACTORS (related)

| Field | Value |
|-------|--------|
| **Surface name** | `EDGARTOOLS_GOLD.FINANCIAL_FACTORS` |
| **Grain** | Same period grain as derived; accounting-only factors |
| **Use** | Ranking screens, 3y/5y CAGRs, liquidity/leverage ratios without market data |
| **Limitations** | Explicitly excludes price / mcap / market ratios — agents join market externally for WACC/PT. |

**ER skill fit:** earnings-analysis / model-update / initiation financials = **Partial → near-Full for GAAP hist**; preview/morning still need consensus (Gap ERDP-01).

---

## 3. EARNINGS_RELEASE

| Field | Value |
|-------|--------|
| **Surface name** | SOURCE `EARNINGS_RELEASE` → gold `EDGARTOOLS_GOLD.EARNINGS_RELEASES` |
| **Grain** | One row per `(cik, accession_number)` (8-K earnings press release) |
| **Key columns** | `cik`, `accession_number`, `filing_date`, `fiscal_year`, `fiscal_quarter`, `period_end`, `revenue_gaap`, `net_income_gaap`, `eps_gaap_diluted`, `has_non_gaap`, `has_guidance`, gold `is_most_recent` / `recency_rank` |
| **How to query** | Latest print: `is_most_recent` or order by `fiscal_year`, `fiscal_quarter`. Join filing timeline via accession → `FILING_ACTIVITY`. Source: edgartools `EarningsRelease` over cached 8-K HTML (Branch B per-filing). |
| **Freshness / watermark** | Available after per-filing fundamentals parse + gold-refresh. `filing_date` is SEC filing date — **not** scheduled earnings call date/time. |
| **Limitations vs ER skills** | **Partial** for earnings skills: GAAP snapshot only. `has_non_gaap` / `has_guidance` are **booleans** — no non-GAAP metric values, no guidance low/mid/high (Gaps → ERDP-02). No consensus beat/miss (no Street estimates → ERDP-01). dbt explicitly does **not** compute beat/miss or EPS streak. No transcript / IR deck (ERDP-04). Not a calendar product (ERDP-03). |

**ER skill fit:** morning-note / earnings-analysis **actuals plug**; cannot satisfy preview consensus table alone.

---

## 4. FILING_ACTIVITY / FILING_DETAIL

### 4.1 FILING_ACTIVITY

| Field | Value |
|-------|--------|
| **Surface name** | `EDGARTOOLS_GOLD.FILING_ACTIVITY` |
| **Grain** | One fact row per filing event (`fact_key`; natural: `accession_number` + company context) |
| **Key columns** | `fact_key`, `company_key`, `filing_key`, `date_key`, `form_key`, `accession_number`, `cik`, `form`, `filing_date`, `report_date`, `is_xbrl` |
| **How to query** | Company timeline: `WHERE cik = ? ORDER BY filing_date DESC`. Form filters (10-K, 10-Q, 8-K, 4, 13F-HR…). Volume analytics: group by form / week. Join `COMPANY` on `company_key` or `cik`. |
| **Freshness / watermark** | Driven by submissions bootstrap + daily incremental → silver `sec_company_filing` → gold. Daily discovery lag is business-day SEC index + pipeline lag. Agent-grade neighborhood does **not** require full filing history inside the bundle — free gold is Explore. |
| **Limitations vs ER skills** | **Partial** filings metadata: form/dates/accession/XBRL flag only. **No** primary document URL/bytes, **no** full text, **no** exhibit inventory in this table. Text: silver `sec_filing_text` (manual/backfill path, not gold product). Bronze S3 holds bytes — not agent contract. |

### 4.2 FILING_DETAIL

| Field | Value |
|-------|--------|
| **Surface name** | `EDGARTOOLS_GOLD.FILING_DETAIL` (dim_filing export) |
| **Grain** | One row per filing (`filing_key` / `accession_number`) |
| **Key columns** | `filing_key`, `accession_number`, `cik`, `company_key`, `form`, `form_key`, `filing_date`, `date_key`, `report_date`, `is_xbrl`, `size` |
| **How to query** | Dimensional join hub for activity facts; lookup by accession; size for “large filing” filters. |
| **Freshness / watermark** | Same as activity. |
| **Limitations vs ER skills** | Same as activity plus `size` only — still not narrative body. Initiation research needs bronze/text/transcript gaps for deep qualitative. |

**ER skill fit:** catalyst/filings cadence, initiation filing lists, earnings “which 10-Q landed” — metadata only.

---

## 5. Ownership / 13F

### 5.1 Ownership (Forms 3/4/5)

| Field | Value |
|-------|--------|
| **Surface names** | `EDGARTOOLS_GOLD.OWNERSHIP_ACTIVITY`, `EDGARTOOLS_GOLD.OWNERSHIP_HOLDINGS` |
| **Grain** | **Activity:** one txn per `(accession_number, owner_index, txn_index)` (`fact_key`). **Holdings:** snapshot per owner/security on filing (`fact_key`). |
| **Key columns** | Activity: `transaction_code`, `transaction_shares`, `transaction_price`, `shares_owned_after`, `is_derivative`, keys to party/security/txn type dims. Holdings: `shares_owned_after`, `ownership_direct_indirect`. |
| **How to query** | Issuer insider flow: filter activity by issuer `company_key`/`cik` + date range + codes (P/S etc.). Owners: join party dim / MDM person. Agent-grade insiders: **graph `IS_INSIDER` ∩ gold ownership source accession** (Subject Bundle `insiders` section) — gold-only names are non-agent-grade. |
| **Freshness / watermark** | Automated ownership parse on Forms 3/4/5 (edgartools `Ownership.from_xml`). Gold after MDM chain + gold-refresh on ownership workflows. |
| **Limitations vs ER skills** | **Partial** for ownership-using skills: transactions and holdings snapshots exist; beneficial ownership % of float, options schedule narrative, and firm “insider watch” process state are not productized. Person dim not fully MDM-joined on gold party keys for all paths. |

### 5.2 13F / institutional holdings

| Field | Value |
|-------|--------|
| **Surface names** | SOURCE `SEC_THIRTEENF_HOLDING` → gold `EDGARTOOLS_GOLD.INSTITUTIONAL_HOLDINGS` |
| **Grain** | One row per `(cik, accession_number, holding_index)` where `cik` is **filing manager** CIK |
| **Key columns** | `period_of_report`, `cusip`, `issuer_name`, `security_title`/`security_class`, `shares_held`, `market_value`, put/call, discretion, voting auth; gold adds QoQ share change, ownership rank within period, recency ranks |
| **How to query** | **Manager book:** `WHERE cik = manager_cik AND period_of_report = latest`. **Holders of issuer:** filter by issuer identity (issuer name/CUSIP; decision sketch uses issuer_cik when projected). Bundle sections: `holders_of_subject` vs `subject_as_manager_portfolio` (separate names). Currency rule: **Latest Complete Holdings Period** + expose `lag_days` (13F is lagged; not same-day positions). |
| **Freshness / watermark** | Branch B thirteenf mode after Branch A; graph `INSTITUTIONAL_HOLDS` when derived. Watermark includes holdings period metadata for agent-grade bundle sections. |
| **Limitations vs ER skills** | **Partial**: no real-time 13F, no short interest, no options-implied ownership. Issuer→holder join quality depends on CUSIP/issuer resolution in MDM security. ADV private funds are a different product (manager bundle). |

---

## 6. Subject Bundle Read

| Field | Value |
|-------|--------|
| **Surface name** | Decision Contract object: **Issuer Subject Bundle** (`build_issuer_subject_bundle`); Manager extension ticket 12 |
| **Code** | `edgar_warehouse/serving/subject_bundle_read.py`; SQL sketch `infra/snowflake/sql/decision_contract/02_subject_bundle_read_issuer.sql` |
| **Grain** | One payload per `(bundle_subject_cik, decision_watermark)` — multi-section neighborhood, not a single fact table |
| **Identity fields** | `bundle_subject_cik`, `bundle_kind` (`issuer` / manager), `decision_contract_version`, `decision_watermark_identity`, `agent_grade`, `agent_grade_reasons` |

### 6.1 Sections (issuer)

| Section | Agent-grade rule | Contents |
|---------|------------------|----------|
| `insiders` | Graph `IS_INSIDER` **and** gold ownership accession | Person + source accessions |
| `employment` | `EMPLOYED_BY` with `proxy_def14a` or `item_5_02`; pay from gold proxy | Employment + executive pay |
| `holders_of_subject` | 13F holders; Latest Complete Holdings Period + lag | Institutional holders of issuer |
| `subject_as_manager_portfolio` | Issuer’s own 13F book (if any) | Separate from holders |
| `auditor` | Prefer auditor evidence + PCAOB id | `AUDITED_BY` / evidence |
| `has_parent` | Only when subsidiary inventory complete; scope `registrant_disclosed` | Parent edges |
| `subject_features` | FY + newer interim pure-SEC vectors (same as Feature Screen) | Feature coverage flags |
| `adv` | Always `not_applicable` on pure issuer | Manager ADV is ticket 12 |

Coverage flags: `present` / `empty` / `unavailable` / `not_applicable` — never silent empty.

### 6.2 How to query (conceptual)

1. Confirm subject in Decision Subject Universe (warehouse active ∩ MDM active).  
2. Assemble watermark components → `evaluate_agent_grade`.  
3. If `agent_grade`, call `build_issuer_subject_bundle(...)` with pre-filtered graph edges + gold rows; else **abstain**.  
4. For multi-name rank/filter without neighborhood: **Subject Feature Screen** (`build_subject_feature_screen`) over pure-SEC keys (`revenue`…`roic` list in serving module).  

### 6.3 Freshness / watermark

Tied to composite Decision Watermark (gold_run_id + graph_generation_id + business_date + completeness/parity). 13F sections carry period lag metadata. Parent section blocked until inventory complete (Exhibit 21 / parser contract).

### 6.4 Limitations vs ER skills

| Need | Bundle status |
|------|----------------|
| Multi-year financial history for model tabs | **Not** full history — as-of FY+interim features only; use free gold `FINANCIAL_DERIVED` in Explore / non-trading research |
| Latest earnings GAAP print | **Not** a first-class bundle section today (map “Not yet specified”: financials_history, latest_earnings, filings_index section adds) |
| Consensus / guidance / transcript / calendar | **Absent** (phase-1 Gaps) |
| Market price / PE / mcap | **Forbidden** on pure-SEC features |
| Thesis / Excel path | Out of platform scope |

**ER skill fit:** idea-generation / initiation qualitative neighborhood, earnings-analysis ownership context — **Partial**; not a drop-in for earnings-preview one-pager inputs.

**Related:** Manager bundle ADV agent-grade only for bulk IAPD `source_system`; heuristic ADV never agent-grade.

---

## 7. MDM entities

| Field | Value |
|-------|--------|
| **Surface names** | Operational MDM (Postgres) + Snowflake mirror: `MDM_COMPANY`, `MDM_PERSON`, `MDM_SECURITY`, `MDM_ADVISER`, `MDM_FUND`, (+ audit firm paths), `MDM_SOURCE_REF`, `MDM_RELATIONSHIP_TYPE`, `MDM_RELATIONSHIP_INSTANCE` |
| **Grain** | **Entity:** one survivorship row per resolved entity id. **Relationship instance:** one active edge instance with type, endpoints, source accession, effective dating. |

### 7.1 Entity domains

| Entity | Key attributes | ER use |
|--------|----------------|--------|
| **company** | CIK, canonical name, ticker/exchange, tracking_status, parent link | Universe, ticker→entity, tracking |
| **person** | Names, owner CIK, officer/director flags | Insider / management |
| **security** | Title, issuer, CUSIP/class | Holdings identity |
| **adviser / fund** | ADV domain | Manager research; secondary for pure equity ER |
| **audit_firm** (via edges/evidence) | Auditor identity | Forensic / auditor section |

### 7.2 How to query (conceptual)

- Resolve ticker/CIK → `MDM_COMPANY` for canonical entity and tracking.  
- List active relationships for a subject entity from `MDM_RELATIONSHIP_INSTANCE` filtered by type and current generation.  
- CLI: `mdm run` → `backfill-relationships` → `export` → `sync-graph` → `verify-graph` (every automated MDM chain).  
- Graph reads should prefer GRAPH_* after parity; MDM is SoE for entities/edges.

### 7.3 Freshness / watermark

MDM export must precede sync-graph so Snowflake MDM mirror is not stale relative to the run. `graph_parity_ok` compares active MDM relationship instances to graph edge counts. Tracking: `bootstrap_pending` → `active` after full submissions bootstrap.

### 7.4 Limitations vs ER skills

MDM is **identity + relationship infrastructure**, not an ER report mart. Sparse edges (e.g. parent inventory incomplete, employment source gaps) surface as empty/unavailable — correct fail-closed behavior. Does not store consensus, transcripts, or thesis. Person resolution quality depends on ownership/proxy source coverage.

**Relationship types (ER-relevant subset):**  
`IS_INSIDER`, `HOLDS`, `COMPANY_HOLDS`, `ISSUED_BY`, `IS_ENTITY_OF`, `HAS_PARENT_COMPANY`, `MANAGES_FUND`, `IS_PERSON_OF`, `EMPLOYED_BY`, `AUDITED_BY`, `INSTITUTIONAL_HOLDS`.

---

## 8. GRAPH_NODES / GRAPH_EDGES

| Field | Value |
|-------|--------|
| **Surface names** | Snowflake `GRAPH_NODES`, `GRAPH_EDGES` (Neo4j Graph Analytics friendly layout) |
| **Hosting** | **Snowflake-hosted only** — not Aura/Bolt/`NEO4J_URI` for supported path (`docs/neo4j.md`) |
| **Grain** | **Nodes:** one row per graph node (`NODEID`, `LABEL`, `PROPERTIES`). **Edges:** one row per relationship (`EDGEID`, `RELATIONSHIP_TYPE`, `SOURCENODEID`, `TARGETNODEID`, `PROPERTIES`) |

### 8.1 How to query (conceptual)

```text
MDM entities/relationships
  → mdm export / sync-graph
  → GRAPH_NODES / GRAPH_EDGES
  → Neo4j Graph Analytics algorithms / SQL over edges
```

- Neighborhood of issuer: edges with subject as source or target, filter `RELATIONSHIP_TYPE`.  
- Validation: edge counts ≡ active MDM relationship instances; zero MDM_MINUS_GRAPH; no missing endpoints.  
- Subject Bundle insiders/auditor/parent consume **graph edges joined to gold evidence**, not graph alone.

### 8.2 Freshness / watermark

`graph_generation_id` is a required watermark component. Stale graph vs gold → **no Agent-Grade Read**. Operator path: `python scripts/ops/neo4j-snowflake-migration.py …` for table apply / hosted e2e.

### 8.3 Limitations vs ER skills

| Need | Graph status |
|------|----------------|
| Trading-relevant neighborhood | **Partial** — present when relationships derived and inventory complete |
| Full ownership history | Prefer gold ownership tables; graph default is **Current** neighborhood |
| Peer comps pack / sector graph | **Gap** as ready-made comps product |
| Properties payload | MDM-derived props; not a full fundamentals store |

**ER skill fit:** initiating-coverage / earnings-analysis / idea-generation qualitative graph context — Partial; never replaces financial statements gold.

---

## 9. Cross-cutting: which surface for which ER job

| ER job (from skills) | Prefer first | Fall back / external |
|----------------------|--------------|----------------------|
| Ticker → CIK / name / SIC | `TICKER_REFERENCE` + `COMPANY` / MDM company | — |
| Multi-year GAAP model hist | `FINANCIAL_DERIVED` / `FINANCIAL_FACTS` | Segment mart (Gap) |
| Screen / rank issuers (pure SEC) | Subject Feature Screen + watermark | Free gold factors (Explore) |
| Deep-dive one name neighborhood | Subject Bundle Read (agent-grade) | Free gold ownership/13F |
| Latest 8-K GAAP print | `EARNINGS_RELEASES` | — |
| Filing timeline | `FILING_ACTIVITY` / `FILING_DETAIL` | Bronze text (backfill) |
| Insider flow | `OWNERSHIP_*` + graph `IS_INSIDER` | Bundle `insiders` |
| 13F holders / manager book | `INSTITUTIONAL_HOLDINGS` + bundle sections | — |
| Auditor / parent | Bundle / graph + evidence tables | Incomplete inventory → unavailable |
| Consensus, guidance values, transcript | **Not on platform** yet (ERDP-01/02/04) | Explore gold when built |
| Earnings **calendar** (forward) | **ERDP-03** `EARNINGS_CALENDAR` Explore (`docs/er-earnings-calendar.md`) | Not `filing_date` |
| Price, mcap, beta, PE, EV, WACC | **ERDP-07** Explore join (`docs/er-market-eod-join.md`) | Never pure-SEC features |
| Thesis / Excel path | N/A platform | Firm process |

---

## 9a. ERDP-03 Earnings calendar (Explore)

| Field | Value |
|-------|--------|
| **Surface name** | `EDGARTOOLS_GOLD.EARNINGS_CALENDAR` ← SOURCE `EARNINGS_CALENDAR` |
| **Code** | `edgar_warehouse.explore.earnings_calendar` |
| **Docs** | `docs/er-earnings-calendar.md` |
| **Grain** | Revision per `(cik, fiscal_year, fiscal_quarter, source_system, as_of)`; `is_current` in dbt |
| **Key fields** | `expected_date`, `expected_time`, `timezone`, `session`, `status`, `source_system`, `as_of` |
| **How to query** | `WHERE is_current AND expected_date BETWEEN …` for catalyst-calendar 2-week list; join `TICKER_REFERENCE` on `cik` |
| **Pilot sources** | `finnhub` (primary), `yahoo` / `firm_manual` fallback |
| **Limitations** | **Explore-only.** Forward schedule ≠ 8-K `filing_date`. Free Finnhub window/license limits. No consensus on this row (ERDP-01). |
| **ER skill fit** | catalyst-calendar, earnings-preview timing, morning-note “who prints today” |

## 9b. ERDP-07 Market EOD join (Explore)

| Field | Value |
|-------|--------|
| **Surface name** | External Explore join — **not** a Gold Snowflake table |
| **Code** | `edgar_warehouse.market` (`PriceProvider`, `eod_join`, `wacc`) |
| **Docs** | `docs/er-market-eod-join.md` |
| **Grain** | One snapshot per `(ticker, as_of)`; CIK resolved via `TICKER_REFERENCE` |
| **Key fields** | `close`, `market_cap`, `beta`, `source_system=yahoo`, `grade=explore` |
| **How to query** | Resolve CIK→ticker from gold `TICKER_REFERENCE`; `eod_snapshot` / `eod_snapshot_for_cik`; EV via `enterprise_value(mcap, debt, cash)` with gold DERIVED; WACC via `compute_wacc` |
| **Freshness** | Live Yahoo EOD (last session ≤ as_of); not Decision Watermark–bound |
| **Limitations vs ER skills** | **Explore-only.** Unblocks valuation-heavy recipes (initiating Task 3, model-update PT, idea/sector multiples). Does **not** replace consensus, guidance, calendar, or transcripts. Forbidden in Agent-Grade `subject_features` (ADR 0001 / ERDP-06). Phase-2 may add Gold MARKET table without changing this boundary. |
| **Caching** | Reuse one `PriceProvider` per batch; see docs §4 (A07.6) |

**ER skill fit:** model-update / initiation / idea / sector valuation = **Partial → runnable Explore** with gold + ERDP-07; full Street print workflow still needs ERDP-01…04.

---

## 10. Acceptance pointers (for coverage matrix after ERDP-04 freeze)

When matrix freeze lands, **Covered** cells that cite existing surfaces should point here with:

1. **Product name** (table or contract object above).  
2. **Read path** (SQL gold / Python serving builder / graph).  
3. **Acceptance** examples:
   - Ticker X resolves to exactly one primary tracked CIK via `TICKER_REFERENCE` + MDM tracking active.  
   - For CIK Y at watermark W, Feature Screen returns FY vector with non-null `revenue` when silver completeness claims period present; nulls remain null.  
   - Bundle for CIK Y returns `agent_grade=true` only if watermark components pass; `insiders` rows all have graph+gold accession.  
   - `EARNINGS_RELEASES.is_most_recent` GAAP fields match latest 8-K parse for CIK.  
   - Graph edge count for type T equals active MDM instances for T under `graph_generation_id`.

**Partial** remains appropriate where only subset of ER skill inputs exist (earnings release without guidance values; filings without text/transcripts).

---

## 11. Draft note for `spec.md` § ERDP-05

> **ERDP-05 Existing-surface ER read map** — Documented in `assets/erdp-05-existing-surface-read-map.md`. Agents read identity via `COMPANY`/`TICKER_REFERENCE` (+ MDM); statements via `FINANCIAL_FACTS`/`FINANCIAL_DERIVED`/`FINANCIAL_FACTORS`; 8-K GAAP via `EARNINGS_RELEASES`; filings via `FILING_ACTIVITY`/`FILING_DETAIL`; ownership via `OWNERSHIP_*`; 13F via `INSTITUTIONAL_HOLDINGS`; neighborhood via Subject Bundle + Feature Screen under Decision Watermark; entities/edges via MDM + `GRAPH_NODES`/`GRAPH_EDGES`. Agent-Grade requires fail-closed watermark. Material ER Gaps (consensus, guidance values, calendar, transcript, market pack) remain ERDP-01…04 / External — not filled by this map.

---

*End of ERDP-05 draft. Promote into `spec.md` and set ticket 05 resolved after ERDP-04 matrix freeze confirms product names in Covered cells.*
