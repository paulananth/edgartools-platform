# ERDP-03 — Earnings Calendar (Detailed Product Spec)

| Field | Value |
|-------|--------|
| **ID** | ERDP-03 |
| **Name** | Earnings calendar |
| **Status** | Implemented (Explore product + dbt + firm_manual/finnhub loaders; ops load TBD) |
| **Pilot source_system** | **`finnhub`** (primary); **`yahoo`** / **`firm_manual`** (fallback) |
| **Milestone** | ER data plane phase-1 |
| **REQUIREMENTS** | `.planning/workstreams/er-data-plane/REQUIREMENTS.md` (ERDP-03-*) |
| **Parent plan** | `.scratch/er-data-plane/spec.md` |
| **Schema sketch** | `.scratch/er-data-plane/assets/erdp-01-04-schema-sketches.md` § ERDP-03 |
| **Free sources research** | `.scratch/er-data-plane/assets/free-data-sources-erdp-01-04.md` |
| **Consumers** | `catalyst-calendar`, `earnings-preview`, `morning-note`, thesis catalyst tables |
| **Layer** | **Gold Explore** SoR; optional MDM keys; **not** graph; **not** pure-SEC Agent-Grade |

---

## 1. Problem statement

ER desks need a **forward-looking** schedule of when companies report (date, pre/post session, confirmed vs estimated).  

Platform today has **reactive** filing dates (`FILING_ACTIVITY`, `EARNINGS_RELEASES.filing_date`) after the fact — **not** a calendar of expected prints.

**ERDP-03** provides that forward calendar product.

---

## 2. Goals and non-goals

### Goals

1. Store **expected report date** per CIK × fiscal quarter.  
2. Capture **session** (`pre_market` / `after_close` / `during_session` / `unknown`).  
3. Optional **clock time** + timezone when available.  
4. **Status**: estimated / confirmed / reported / cancelled.  
5. Support **as_of** verification time for stale calendar hygiene.  
6. Provider-agnostic + firm_manual.  
7. Explore-only.

### Non-goals

| Out | Elsewhere |
|-----|-----------|
| Consensus EPS on the calendar row | ERDP-01 (join by period) |
| Guidance values | ERDP-02 |
| Macro calendars (FOMC, CPI) | External / out of phase-1 |
| Transcript scheduling | ERDP-04 event_date may differ from print time |
| Replacing 8-K filing_date | Filings remain source of “reported” truth |

---

## 3. User stories

1. **As** `catalyst-calendar`, list all coverage names reporting in the next 14 days with session.  
2. **As** `earnings-preview`, know print date/time for company T.  
3. **As** `morning-note`, know who prints today pre-market vs after-close.  
4. **As** ops, mark a row `confirmed` from IR or firm research.

---

## 4. Data product definition

### 4.1 Conceptual model

One row = current (or versioned) **expectation** for one issuer’s earnings **event** for one fiscal quarter/year.

**Forward-looking** ≠ post-hoc `filing_date`.

### 4.2 Natural key and current view

**Base key (multi-source):**

```text
(cik, fiscal_year, fiscal_quarter, source_system)
```

**Current row:** max(`as_of`), then max(`ingested_at`) for that key.  

Optional history table later: `EARNINGS_CALENDAR_SNAPSHOT` if full revision history required (phase-1: overwrite or insert-new with as_of only is enough if key includes as_of — **prefer key without as_of + update in place for “current”, retain prior via SCD2 or history table if cheap**).

**Recommended phase-1:**  
Natural key `(cik, fiscal_year, fiscal_quarter, source_system, as_of)` to keep revisions; “current” = latest as_of query.

### 4.3 Relation to filings

```text
When 8-K earnings files:
  calendar status → reported
  (optional) link accession_number on calendar row
```

Do not delete estimated rows; transition status.

---

## 5. Logical schema (normative)

### 5.1 Names

| Layer | Name |
|-------|------|
| Silver | `ext_earnings_calendar` (or `sec_earnings_calendar` if hybrid) |
| Gold | `EARNINGS_CALENDAR` |
| dbt | `EDGARTOOLS_GOLD.EARNINGS_CALENDAR` |

### 5.2 Columns

| Column | Type | Null | Description |
|--------|------|:----:|-------------|
| `fact_key` | int64 | N | Surrogate |
| `cik` | int64 | N | |
| `ticker` | string | Y | |
| `company_key` | int64 | Y | |
| `fiscal_year` | int32 | N | |
| `fiscal_quarter` | int32 | N | 1–4 |
| `expected_date` | date | N | Calendar date of announcement |
| `expected_time` | string | Y | `HH:MM` (24h) |
| `timezone` | string | Y | IANA, e.g. `America/New_York` |
| `session` | string | N | `pre_market` \| `after_close` \| `during_session` \| `unknown` |
| `status` | string | N | `estimated` \| `confirmed` \| `reported` \| `cancelled` |
| `period_end` | date | Y | Fiscal period end |
| `accession_number` | string | Y | Set when reported / linked |
| `source_system` | string | N | `yahoo` \| `finnhub` \| `fmp` \| `firm_manual` \| `other` |
| `source_ref` | string | Y | |
| `as_of` | date | N | When this schedule fact was verified |
| `ingested_at` | timestamp | N | |

### 5.3 Integrity

1. `session` required; for `status=confirmed`, prefer not `unknown` (A03.2).  
2. `expected_date` required.  
3. Map vendor BMO→`pre_market`, AMC→`after_close`.  
4. No market-price columns.

---

## 6. Vocabularies

### 6.1 Session mapping

| Vendor label | `session` |
|--------------|-----------|
| BMO, before market, pre-market | `pre_market` |
| AMC, after market, after close | `after_close` |
| During, DMA | `during_session` |
| Missing / TBD | `unknown` |

### 6.2 Status lifecycle

```text
estimated → confirmed → reported
     ↘ cancelled
```

---

## 7. Source and ingestion

### 7.1 Free / freemium pilots

| source_system | Strength | Weakness |
|---------------|----------|----------|
| `finnhub` | API, bmo/amc | Rate limits, history window |
| `yahoo` | Broad calendar | Scrape/unofficial |
| `fmp` | API calendar | Time field unstable historically |
| `firm_manual` | Controlled pilot | Ops cost |

### 7.2 Pipeline sketch

```text
Daily job: pull next N days / full quarter for tracked universe
  → map tickers to CIK
  → upsert EARNINGS_CALENDAR
  → optional: reconcile status=reported when EARNINGS_RELEASES appears
```

**Universe:** Decision Subject Universe / MDM tracked companies (define sample for A03.1).

### 7.3 Reconciliation with SEC

When `EARNINGS_RELEASES` or 8-K Item 2.02 lands for (cik, FY, FQ):

- Set matching calendar rows to `status=reported`  
- Optionally set `accession_number`  
- Do not change historical estimated as_of rows if using multi-as_of key

---

## 8. Query patterns

### 8.1 Next 14 days for coverage list

```sql
SELECT *
FROM EDGARTOOLS_GOLD.EARNINGS_CALENDAR
WHERE cik IN (/* coverage */)
  AND status IN ('estimated', 'confirmed')
  AND expected_date BETWEEN CURRENT_DATE() AND DATEADD(day, 14, CURRENT_DATE())
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY cik, fiscal_year, fiscal_quarter, source_system
  ORDER BY as_of DESC
) = 1
ORDER BY expected_date, session;
```

### 8.2 Today’s prints by session

```sql
... AND expected_date = CURRENT_DATE() AND session = 'pre_market'
```

---

## 9. Acceptance criteria

| ID | Criterion |
|----|-----------|
| **A03.1** | Sample ≥10 tracked tickers: ≥80% have forward quarter row OR just-reported `status=reported`. Sample universe = MDM tracked / Decision Subject Universe. |
| **A03.2** | Confirmed rows: `session` ≠ `unknown` (or documented waiver rate). |
| **A03.3** | Doc: catalyst-calendar 2-week list from this table alone. |
| **A03.4** | Explore-only labeling. |
| **A03.5** | `expected_time`/`timezone` columns exist; null allowed on free sources. |
| **A03.6** | firm_manual load for 3 CIKs. |
| **A03.7** | Optional: auto `reported` when gold earnings release matches period. |

---

## 10. REQUIREMENTS checklist

- [x] ERDP-03-01…07 (see REQUIREMENTS.md)  
- [x] A03.5–A03.7 (columns + firm_manual + mark_reported)  
- [x] Schema/export/dbt  
- [x] Document sample universe for A03.1 (`coverage_for_universe` + docs)  

### 10.1 Implementation map (2026-07-24)

| Piece | Location |
|-------|----------|
| Domain / loaders | `edgar_warehouse/explore/earnings_calendar.py` |
| Gold schema | `gold_schemas.yaml` `_FACT_EARNINGS_CALENDAR_SCHEMA` |
| Export | `write_earnings_calendar_to_serving_export`; `SNOWFLAKE_EXPORT_TABLES` |
| dbt | `models/gold/earnings_calendar.sql` + sources.yml |
| Docs | `docs/er-earnings-calendar.md` |
| Tests | `tests/unit/test_earnings_calendar.py` |

---

## 11. Open design decisions

| # | Decision | Default |
|---|----------|---------|
| D1 | Pilot source | **Locked: `finnhub` primary; `yahoo` / `firm_manual` fallback** |
| D2 | History model | key includes `as_of` |
| D3 | Timezone default when missing | `America/New_York` for US issuers only as display default, store null if unknown |
| D4 | Annual-only reporters | fiscal_quarter=4 or special period_type — document |

### 11.1 Pilot source lock (2026-07-25)

| Role | source_system | Notes |
|------|---------------|--------|
| Primary | `finnhub` | Free calendar API; bmo/amc/dmh → session; free history window limited; **check personal-use license** before commercial gold |
| Fallback | `yahoo` | Web/scraper/`get_earnings_dates`; fragile |
| Fallback | `firm_manual` | Confirmed IR dates for pilot names |
| Session map | — | bmo→`pre_market`, amc→`after_close`, dmh→`during_session` |
| `expected_time` | — | Null allowed on free pilot |

---

## 12. Traceability

Parent plan, REQs, free-data note, ER skill I/O, ADR 0001.

---

*Spec version 1.1 — Explore implementation landed; commercial Finnhub license still ops gate.*
