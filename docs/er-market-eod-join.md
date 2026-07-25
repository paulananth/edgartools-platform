# ER market EOD join (ERDP-07)

**Status:** phase-1 Explore contract  
**Pilot source:** Yahoo Finance via `yfinance` / `edgar_warehouse.market.price_provider.PriceProvider`  
**Grade:** **Explore only** — never Agent-Grade Decision Features  
**ADR:** [0001-agent-decision-surface-first.md](./adr/0001-agent-decision-surface-first.md)  
**Planning:** `.scratch/er-data-plane/specs/ERDP-07-market-eod-join.md`, `.planning/workstreams/er-data-plane/REQUIREMENTS.md`

This document is the consumer-facing join contract for free end-of-day market
data used by equity-research (ER) valuation recipes. It does **not** introduce a
Snowflake Gold `MARKET_*` table (that remains phase-2 optional).

---

## 1. Boundary (ERDP-06)

| Allowed | Forbidden |
|---------|-----------|
| Explore / research / ER valuation notebooks and skills | Injecting close, mcap, beta, PE, EV into pure-SEC `subject_features` |
| Human Audit **Explore** mode labeled not-for-agent | Agent View Mode Decision Contract fields for price/mcap |
| Label outputs `grade=explore`, `source_system=yahoo` | Treating Yahoo as pure-SEC or Decision Watermark input |

```text
Agent-Grade Decision Contract  →  pure-SEC only (no ERDP-07 fields)

Explore / research / ER valuation
  →  Gold fundamentals  ⋈  ERDP-07 PriceProvider(ticker, as_of)
  →  Label Explore; cite source_system=yahoo
```

Market data is **not** a Decision Watermark component. Agent-Grade fail-closed
rules in [decision-watermark.md](./decision-watermark.md) are unchanged.

---

## 2. Join contract

### 2.1 Keys

| Key | Role |
|-----|------|
| `ticker` | Primary key for yfinance |
| `cik` | Resolve via gold `TICKER_REFERENCE` (or MDM company ticker) → primary ticker |
| `as_of` | ISO date `YYYY-MM-DD`; provider uses last available session **≤** `as_of` |

### 2.2 Resolve CIK → ticker

```sql
-- Conceptual gold SQL
SELECT cik, ticker, exchange
FROM EDGARTOOLS_GOLD.TICKER_REFERENCE
WHERE cik = ?
```

Python helper (no network):

```python
from edgar_warehouse.market import pick_primary_ticker, eod_snapshot_for_cik

ticker = pick_primary_ticker(ticker_rows, cik="0000320193")
# or end-to-end:
snap = eod_snapshot_for_cik(pp, ticker_rows, cik="0000320193", as_of="2024-12-31")
```

`pick_primary_ticker` prefers major exchanges (NASDAQ/NYSE/…) when multiple
tickers exist for one CIK.

### 2.3 Minimum fields

| Field | Source |
|-------|--------|
| `close` | yfinance adjusted close (session ≤ as_of) |
| `market_cap` | close × shares outstanding (yfinance) |
| `beta` | yfinance trailing beta |
| `currency` | USD for US pilot |
| `source_system` | always `yahoo` for this pilot path |
| `grade` | always `explore` |

Optional gold join (prefer gold for shares when building custom mcap):

| Gold field | Use |
|------------|-----|
| `FINANCIAL_DERIVED.shares_outstanding` | Prefer over yfinance shares when present |
| `FINANCIAL_DERIVED` debt / cash | Enterprise value (below) |
| `FINANCIAL_DERIVED` EPS / EBITDA / revenue | Multiples |

### 2.4 Derived

| Output | Formula |
|--------|---------|
| Equity value | `market_cap` |
| Enterprise value | `market_cap + total_debt − cash` |
| EV/EBITDA, P/E, EV/Sales | EV or price + gold earnings / EBITDA / revenue |
| WACC | `compute_wacc` + gold debt/tax + market Ke |
| Upside to model PT | `(pt − spot) / spot` |

```python
from edgar_warehouse.market import PriceProvider, enterprise_value, eod_snapshot

pp = PriceProvider()
snap = eod_snapshot(pp, "AAPL", "2024-12-31")
ev = enterprise_value(snap.market_cap, total_debt=1.1e11, cash=3e10)
```

---

## 3. Python API

Install optional deps:

```bash
uv sync --extra market
# or transient:
uv run --with yfinance --with fredapi python …
```

| Symbol | Module | Purpose |
|--------|--------|---------|
| `PriceProvider` | `market.price_provider` | close, mcap, beta, FRED rf, Damodaran ERP |
| `eod_snapshot` / `eod_snapshot_for_cik` | `market.eod_join` | Explore snapshot dict/dataclass |
| `pick_primary_ticker` | `market.eod_join` | CIK → ticker from reference rows |
| `enterprise_value` | `market.eod_join` | mcap + debt − cash |
| `batch_eod_snapshots` | `market.eod_join` | multi-ticker with shared cache |
| `compute_wacc` / `WaccInputs` | `market.wacc` | CAPM WACC |

---

## 4. Caching and batch guidance (A07.6)

1. **One `PriceProvider` per batch** — prices, beta, and rf are cached in-memory
   on the instance. Do not construct a new provider per ticker.
2. **Screens:** use `batch_eod_snapshots(..., include_beta=False)` unless beta is
   required (WACC). Beta and info endpoints are heavier than history downloads.
3. **Do not hammer Yahoo** — no unbounded per-row live calls inside tight loops
   over full universes without caching; for large universes prefer a local cache
   file/session or a future Gold MARKET table (phase-2).
4. **Retries:** treat `None` close as missing data; avoid tight retry loops on
   rate limits. Prefer next business day or documented override.
5. **FRED:** risk-free rate needs `FRED_API_KEY` (or pass into `PriceProvider`);
   WACC falls back to 4% with a warning when rf is unavailable.
6. **Offline / CI:** unit tests use overrides and mocks; live Yahoo checks are
   opt-in (see tests marked with network requirements).

---

## 5. ER skill recipes (A07.5)

All recipes are **Explore**. Cite `source_system=yahoo` and gold accession /
period keys for fundamentals.

### 5.1 Model-update — PT / multiples refresh

1. Load latest `FINANCIAL_DERIVED` for CIK (actuals after print).  
2. Resolve ticker via `TICKER_REFERENCE`.  
3. `eod_snapshot(pp, ticker, as_of=business_date)` → spot, mcap.  
4. `enterprise_value(mcap, total_debt, cash)` from gold balance sheet.  
5. Multiples: `spot / eps_diluted`, `ev / ebitda`, `ev / revenue`.  
6. Optional: `compute_wacc` + DCF / model PT from firm Excel;  
   upside = `(model_pt − spot) / spot`.  
7. Label table **Explore**; do not write multiples into Subject Bundle features.

### 5.2 Initiating-coverage Task 3 — WACC, comps, DCF PT

1. Gold multi-year FCF / earnings history for subject + peer CIKs.  
2. Peer tickers from `TICKER_REFERENCE`; batch EOD for peers.  
3. Subject WACC:

```python
from edgar_warehouse.market import PriceProvider, WaccInputs, compute_wacc

pp = PriceProvider()  # single instance for the whole batch
result = compute_wacc(
    WaccInputs(
        ticker="AAPL",
        period_end="2024-09-28",
        sic_code="3571",
        total_debt=…,          # gold
        interest_expense=…,
        income_tax_expense=…,
        pretax_income=…,
    ),
    price_provider=pp,
)
```

4. Trading comps: peer EV/EBITDA, P/E from gold + EOD.  
5. Simple DCF: project FCF, discount at WACC → equity value / share → PT.  
6. Charts: price series is Explore-only (yfinance history outside this contract
   is fine for human decks).

### 5.3 Idea-generation — value screen

1. Feature Screen or gold factors for pure-SEC ranks (Agent-Grade path if
   watermarked — **without** prices).  
2. For Explore value overlays: join EOD mcap → earnings yield, FCF yield,
   EV/EBITDA vs peers.  
3. Keep ranking that feeds trading agents pure-SEC unless an explicit Explore
   policy is approved.

### 5.4 Sector-overview — relative multiples

1. SIC peer set from `COMPANY` / gold ranks.  
2. Batch EOD closes/mcaps for peer tickers.  
3. Sector median EV/EBITDA, P/E as Explore tables.

### 5.5 Earnings note / preview — valuation section

1. Spot and % move (recent as_of vs prior session) for trading setup.  
2. Upside to model PT; mcap context.  
3. Consensus beat/miss still requires ERDP-01 (not prices).

---

## 6. Acceptance criteria

| ID | Criterion | How checked |
|----|-----------|-------------|
| **A07.1** | ≥5 liquid US tickers: non-null close on a recent trading day | Live or mocked `get_price` tests |
| **A07.2** | CIK→ticker→price for ≥5 sample CIKs | `pick_primary_ticker` + snapshot path |
| **A07.3** | `compute_wacc` succeeds for ≥1 name with debt + mcap/beta | Unit + optional live |
| **A07.4** | Explore-only / forbidden in pure-SEC features | This doc + ADR 0001 |
| **A07.5** | ER recipes documented | §5 above |
| **A07.6** | Caching / batch guidance | §4 above |

---

## 7. Related surfaces

| Surface | Role |
|---------|------|
| `TICKER_REFERENCE` / `COMPANY` | Identity join |
| `FINANCIAL_DERIVED` / `FINANCIAL_FACTS` | Debt, cash, earnings, shares |
| Subject Feature Screen / Bundle | Pure-SEC only — no ERDP-07 fields |
| ERDP-01…04 | Consensus, guidance, calendar, transcript (separate Explore gold) |
| Phase-2 Gold MARKET table | Optional productized daily prices — not this milestone |

ER read map: `.scratch/er-data-plane/assets/erdp-05-existing-surface-read-map.md`  
Skill unblock matrix: `.scratch/er-data-plane/assets/er-skills-unblocked-with-eod.md`

---

*ERDP-07 implementation docs — 2026-07-24*
