# ER consensus estimates (ERDP-01)

**Status:** phase-1 Gold Explore product
**Pilot sources:** `yahoo` (primary automated), `firm_manual` (fallback), `fmp` (optional, not implemented)
**Grade:** **Explore only** — not pure-SEC Agent-Grade Decision Features
**ADR:** [0001-agent-decision-surface-first.md](./adr/0001-agent-decision-surface-first.md)
**Spec:** `.scratch/er-data-plane/specs/ERDP-01-consensus-estimates.md`
**Code:** `edgar_warehouse.explore.consensus_estimates`

Street (or proxy) consensus statistics for revenue, EPS, and related
metrics, keyed by issuer, fiscal period, and a snapshot `as_of` date. Used
to build pre-print previews and to compute beat/miss against actuals —
beat/miss is **computed at query time**, never stored in this table.

---

## 1. Product

| Layer | Name |
|-------|------|
| Gold export / SOURCE | `CONSENSUS_ESTIMATES` |
| dbt dynamic table | `EDGARTOOLS_GOLD.CONSENSUS_ESTIMATES` |
| Python builder | `build_consensus_estimates_table` / `build_consensus_estimates_table_from_rows` |
| Serving write | `write_consensus_estimates_to_serving_export` |

### Natural key

```text
(cik, metric, period_type, fiscal_year, fiscal_quarter, statistic, as_of, source_system)
```

**Current view:** `is_current` in dbt = latest `as_of` (then `ingested_at`) per
`(cik, metric, period_type, fiscal_year, fiscal_quarter, statistic, source_system)`.

### Columns (minimum)

`fact_key`, `cik`, `ticker`, `company_key`, `metric`, `period_type`,
`fiscal_year`, `fiscal_quarter`, `period_end`, `estimate_value`, `unit`,
`currency`, `statistic`, `as_of`, `source_system`, `source_ref`, `ingested_at`.

| `period_type` | Meaning |
|---------------|---------|
| `annual` | Full fiscal year — `fiscal_quarter` forced to `0` (D2) |
| `quarterly` | Single fiscal quarter — `fiscal_quarter` required, 1–4 |
| `ntm` | Next-twelve-months — `fiscal_year`/`fiscal_quarter` may be null |
| `ltm` | Last-twelve-months — `fiscal_year`/`fiscal_quarter` may be null |
| `other` | Anything not covered above |

| `statistic` | Meaning |
|--------------|---------|
| `mean` | Consensus average |
| `median` | Consensus median (when a vendor only reports median, emit as `median` not `mean`) |
| `high` / `low` | Range bounds, as separate rows |
| `stdev` | Standard deviation |
| `n_analysts` | Analyst count backing the estimate |

Phase-1 metric minimum (ERDP-01-06): `revenue`, `eps_diluted` must be
accepted; `ebitda`, `net_income`, `eps_basic`, `gross_profit` also allowed.
Unknown metrics are rejected (`ConsensusRowError`), not silently coerced.

No price / mcap / PE / EV columns (ERDP-06).

---

## 2. Load paths

### 2.1 firm_manual (CSV) — ERDP-01-07

```csv
cik,ticker,metric,period_type,fiscal_year,fiscal_quarter,estimate_value,as_of
320193,AAPL,revenue,quarterly,2026,3,95000,2026-06-01
320193,AAPL,eps_diluted,quarterly,2026,3,1.42,2026-06-01
```

```python
from edgar_warehouse.explore.consensus_estimates import (
    load_firm_manual_csv,
    build_consensus_estimates_table,
)
from edgar_warehouse.serving.targets.snowflake import (
    write_consensus_estimates_to_serving_export,
)

rows = load_firm_manual_csv("pilot_consensus.csv")
table = build_consensus_estimates_table(rows)
# write_consensus_estimates_to_serving_export(table, export_root, run_id, business_date)
```

`source_system` and `statistic` default to `firm_manual` / `mean` when omitted.

### 2.2 yahoo (automated pilot, via yfinance) — ERDP-01-08

```python
from edgar_warehouse.explore.consensus_estimates import fetch_yahoo_consensus_estimates

rows = fetch_yahoo_consensus_estimates(
    cik=320193,
    ticker="AAPL",
    # yfinance's earnings/revenue estimate frames use relative period
    # labels (0q/+1q/0y/+1y), not absolute fiscal periods -- the caller
    # resolves each label to a real fiscal_year/fiscal_quarter (e.g. from
    # FILING_ACTIVITY or the company's known fiscal calendar).
    period_resolution={
        "0q": {"period_type": "quarterly", "fiscal_year": 2026, "fiscal_quarter": 3},
        "+1q": {"period_type": "quarterly", "fiscal_year": 2026, "fiscal_quarter": 4},
    },
)
```

Requires the optional `[market]` extra (`yfinance`). Free/unofficial API —
fragile, and ToS must be confirmed before a commercial gold load (A01.7).
`parse_yahoo_consensus_estimate` is the pure parser (no network call) if you
already have a fetched frame, e.g. for tests or a cached payload.

---

## 3. Query patterns

### Current consensus (latest as_of)

```sql
SELECT *
FROM EDGARTOOLS_GOLD.CONSENSUS_ESTIMATES
WHERE is_current
  AND cik = ? AND metric = 'eps_diluted'
  AND period_type = 'quarterly'
  AND fiscal_year = ? AND fiscal_quarter = ?
  AND statistic = 'mean';
```

### Pre-print consensus for beat/miss (A01.5)

```sql
SELECT *
FROM EDGARTOOLS_GOLD.CONSENSUS_ESTIMATES
WHERE cik = ?
  AND metric IN ('revenue', 'eps_diluted')
  AND statistic = 'mean'
  AND as_of <= ?   -- print date
  AND fiscal_year = ? AND fiscal_quarter = ?
ORDER BY as_of DESC;
```

Beat/miss itself is computed by joining the result to `EARNINGS_RELEASES` or
`FINANCIAL_DERIVED` actuals at query time — it is never persisted in
`CONSENSUS_ESTIMATES`, to avoid coupling this table to the actuals pipeline.

### Join identity

```sql
SELECT c.*, t.ticker AS ref_ticker
FROM EDGARTOOLS_GOLD.CONSENSUS_ESTIMATES c
LEFT JOIN EDGARTOOLS_GOLD.TICKER_REFERENCE t
  ON c.cik = t.cik
WHERE c.is_current;
```

---

## 4. Acceptance

| ID | Criterion |
|----|-----------|
| **A01.1** | Sample CIK: ≥1 row each for `eps_diluted` and `revenue` for latest completed FQ with non-null `as_of` |
| **A01.2** | Two different `as_of` for the same period both retained (no silent overwrite; `is_current` is a read-time projection, not a filter applied before publish) |
| **A01.3** | Explore-only labeling (this doc) |
| **A01.4** | Sample rows join to `COMPANY` / `TICKER_REFERENCE` on `cik` |
| **A01.5** | Beat/miss query recipe documented (§3) |
| **A01.6** | firm_manual CSV round-trip for ≥1 CIK |
| **A01.7** | Free-pilot path documented with ToS caveat (this doc, §2.2) |

---

## 5. Related

- [er-guidance-facts.md](./er-guidance-facts.md) — company-issued guidance is a separate product (ERDP-02)
- [er-earnings-calendar.md](./er-earnings-calendar.md) — forward-looking print dates (ERDP-03)
- [er-market-eod-join.md](./er-market-eod-join.md) — prices are separate (ERDP-07)
- Reactive actuals: `EDGARTOOLS_GOLD.EARNINGS_RELEASES`, `EDGARTOOLS_GOLD.FINANCIAL_DERIVED`
