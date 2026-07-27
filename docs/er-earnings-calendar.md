# ER earnings calendar (ERDP-03)

**Status:** phase-1 Gold Explore product  
**Pilot sources:** `finnhub` (primary, license-gated — not yet cleared), `firm_manual` (fallback, doesn't scale to a coverage-universe-wide need). **`yahoo` is not implemented** despite being referenced below and in `SOURCE_SYSTEMS` — no `parse_yahoo_*`/`fetch_yahoo_*` function exists in `earnings_calendar.py` (confirmed 2026-07-27, `.scratch/erdp-coverage-promotion/issues/07-free-earnings-calendar-sources.md`). Planned real path: Alpha Vantage `EARNINGS_CALENDAR` (see §5 below) — not yet built.  
**Grade:** **Explore only** — not pure-SEC Agent-Grade Decision Features  
**ADR:** [0001-agent-decision-surface-first.md](./adr/0001-agent-decision-surface-first.md)  
**Spec:** `.scratch/er-data-plane/specs/ERDP-03-earnings-calendar.md`  
**Code:** `edgar_warehouse.explore.earnings_calendar`

Forward-looking schedule of when issuers are **expected** to report. This is
**not** the same as reactive `EARNINGS_RELEASES.filing_date` (after the 8-K).

---

## 1. Product

| Layer | Name |
|-------|------|
| Gold export / SOURCE | `EARNINGS_CALENDAR` |
| dbt dynamic table | `EDGARTOOLS_GOLD.EARNINGS_CALENDAR` |
| Python builder | `build_earnings_calendar_table` / `build_earnings_calendar_table_from_rows` |
| Serving write | `write_earnings_calendar_to_serving_export` |

### Natural key

```text
(cik, fiscal_year, fiscal_quarter, source_system, as_of)
```

**Current view:** `is_current` in dbt = latest `as_of` (then `ingested_at`) per
`(cik, fiscal_year, fiscal_quarter, source_system)`.

### Columns (minimum)

`fact_key`, `cik`, `ticker`, `company_key`, `fiscal_year`, `fiscal_quarter`,
`expected_date`, `expected_time`, `timezone`, `session`, `status`, `period_end`,
`accession_number`, `source_system`, `source_ref`, `as_of`, `ingested_at`.

| `session` | Meaning |
|-----------|---------|
| `pre_market` | BMO / before open |
| `after_close` | AMC / after close |
| `during_session` | During market hours |
| `unknown` | Not supplied (allowed for `estimated` only) |

| `status` | Lifecycle |
|----------|-----------|
| `estimated` | Provider best guess |
| `confirmed` | IR / firm confirmed — **session must not be `unknown`** (A03.2) |
| `reported` | 8-K / earnings release observed |
| `cancelled` | Print cancelled / postponed without new date |

No price / mcap / PE columns (ERDP-06).

---

## 2. Load paths

### 2.1 firm_manual (CSV) — ERDP-03-06

```csv
cik,ticker,fiscal_year,fiscal_quarter,expected_date,session,status,as_of
320193,AAPL,2025,3,2025-07-31,after_close,confirmed,2025-07-01
789019,MSFT,2025,4,2025-07-30,after_close,confirmed,2025-07-01
1652044,GOOGL,2025,2,2025-07-29,after_close,confirmed,2025-07-01
```

```python
from edgar_warehouse.explore.earnings_calendar import (
    load_firm_manual_csv,
    build_earnings_calendar_table,
)
from edgar_warehouse.serving.targets.snowflake import (
    write_earnings_calendar_to_serving_export,
)

rows = load_firm_manual_csv("pilot_calendar.csv")
table = build_earnings_calendar_table(rows)
# write_earnings_calendar_to_serving_export(table, export_root, run_id, business_date)
```

### 2.2 finnhub (automated pilot) — ERDP-03-07

```bash
export FINNHUB_API_KEY=...
```

```python
from datetime import date, timedelta
from edgar_warehouse.explore.earnings_calendar import (
    fetch_finnhub_earnings_calendar,
    build_earnings_calendar_table,
)

today = date.today()
rows = fetch_finnhub_earnings_calendar(
    from_date=today,
    to_date=today + timedelta(days=90),
    ticker_to_cik={"AAPL": 320193, "MSFT": 789019},
)
table = build_earnings_calendar_table(rows)
```

Maps Finnhub `hour`: `bmo`→`pre_market`, `amc`→`after_close`, `dmh`→`during_session`.

**License:** verify Finnhub free-tier terms before commercial gold publication.
If blocked, use `firm_manual` (doesn't scale to universe-wide) or implement
the Alpha Vantage path (§5 below) — **not** `yahoo`, which despite being
named here and in `SOURCE_SYSTEMS` has no implementation.

### 2.3 Mark reported from gold releases (A03.7)

```python
from edgar_warehouse.explore.earnings_calendar import mark_reported

updated = mark_reported(calendar_rows, earnings_release_rows)
```

Matches `(cik, fiscal_year, fiscal_quarter)`; emits new `as_of` revision with
`status=reported` and optional `accession_number`.

---

## 3. Query patterns (A03.3 catalyst-calendar)

### Next 14 days for coverage list

```sql
SELECT cik, ticker, fiscal_year, fiscal_quarter,
       expected_date, expected_time, timezone, session, status, source_system
FROM EDGARTOOLS_GOLD.EARNINGS_CALENDAR
WHERE is_current
  AND cik IN (/* coverage CIKs */)
  AND status IN ('estimated', 'confirmed')
  AND expected_date BETWEEN CURRENT_DATE() AND DATEADD(day, 14, CURRENT_DATE())
ORDER BY expected_date, session;
```

Python helper (in-memory, no Snowflake):

```python
from edgar_warehouse.explore.earnings_calendar import next_n_days

upcoming = next_n_days(rows, days=14, ciks=coverage_ciks)
```

### Today by session

```sql
... AND expected_date = CURRENT_DATE() AND session = 'pre_market'
```

### Join identity

```sql
SELECT c.*, t.ticker AS ref_ticker
FROM EDGARTOOLS_GOLD.EARNINGS_CALENDAR c
LEFT JOIN EDGARTOOLS_GOLD.TICKER_REFERENCE t
  ON c.cik = t.cik
WHERE c.is_current;
```

---

## 4. Acceptance

| ID | Criterion |
|----|-----------|
| **A03.1** | ≥10 universe CIKs: ≥80% have forward row or `reported` (`coverage_for_universe`) |
| **A03.2** | `confirmed` ⇒ `session` ≠ `unknown` (enforced in normalize) |
| **A03.3** | Next-2-week list from this table alone (SQL / `next_n_days`) |
| **A03.4** | Explore-only labeling (this doc) |
| **A03.5** | `expected_time` / `timezone` columns exist; null OK on free pilot |
| **A03.6** | firm_manual CSV for ≥3 CIKs |
| **A03.7** | Optional `mark_reported` when releases match period |

---

## 5. Promotion checklist (Partial → Covered)

**Current coverage-matrix status: Partial, not Covered** (`.scratch/er-data-plane/coverage-matrix.md` F18). Full reasoning and source citations: `.scratch/erdp-coverage-promotion/issues/05-promotion-criteria-earnings-calendar.md` and `07-free-earnings-calendar-sources.md`.

**Build prerequisite — not yet done.** Neither real path today (`finnhub`, license-gated; `firm_manual`, doesn't scale) can satisfy catalyst-calendar/morning-note's coverage-universe-wide, every-trading-day need. Deep research into free alternatives (yfinance, Nasdaq's internal API, SEC, Alpha Vantage) found **Alpha Vantage's `EARNINGS_CALENDAR`** is the only candidate that's genuinely bulk, official/documented, and ToS-clean — yfinance's per-ticker earnings-date function is confirmed literal HTML scraping in the pinned version, and Nasdaq's endpoint (which does have real session-timing data) is undocumented with `robots.txt: Disallow: /` on the whole subdomain. Alpha Vantage is date-only (no session timing — no free ToS-clean source has any); accepted as `session="unknown"`, already a legitimate enum value. **To build:** add `"alphavantage"` to `SOURCE_SYSTEMS`; implement a fetch/parse function calling `EARNINGS_CALENDAR` with `symbol` omitted (bulk mode, respecting the 25-req/day free-tier ceiling).

| # | Criterion |
|---|-----------|
| 0 | *(prerequisite above)* |
| 1 | `source_system ∈ {finnhub, firm_manual, alphavantage}` — `yahoo`/`fmp`/`other` disqualify |
| 2 | At least one **bulk** source (`finnhub` or `alphavantage`) active, covering ≥90% of the Decision Subject Universe for the current+next fiscal quarter — `firm_manual` alone cannot pass this by construction, not a measured gap |
| 3 | `finnhub` rows: `source_ref` matches `^finnhub:calendar/earnings:[^:]+:[0-9]{4}:Q[1-4]$` (real format, `earnings_calendar.py:369`) |
| 4 | `alphavantage` rows (once built): deterministic `source_ref` format specified at implementation time, same authenticity-check convention |
| 5 | `firm_manual` rows trace to a checked-in, git-reviewed CSV |
| 6 | `confirmed` rows never use `session=unknown` (already enforced — A03.2); `estimated` rows may |
| 7 | Staleness re-verification: a row `as_of` >X days old with `expected_date` in the next 2 weeks must have a fresher re-confirming row, not be served stale (catalyst-calendar's own "dates shift" caveat) |
| 8 | 100% join to `COMPANY`/`TICKER_REFERENCE`, identity-checked |
| 9 | Explore-only labeling re-affirmed |

**Not required for promotion:** exact time-of-day beyond session bucketing; history — every consumer wants only the *next* occurrence.

**Residual risk:** criterion 7 depends on the upstream vendor actually re-publishing changed dates promptly — no acceptance query against the platform's own data can detect silent vendor staleness without an independent second source.

---

## 6. Related

- [er-market-eod-join.md](./er-market-eod-join.md) — prices are separate (ERDP-07)  
- Reactive actuals: `EDGARTOOLS_GOLD.EARNINGS_RELEASES`  
- ERDP-01 consensus joins on `(cik, FY, FQ)` for beat/miss once published  

---

*ERDP-03 implementation docs — 2026-07-24*
