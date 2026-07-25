# ERDP-07 — Market EOD join (Explore)

| Field | Value |
|-------|--------|
| **ID** | ERDP-07 |
| **Name** | Market end-of-day price join |
| **Status** | Implemented (Explore join + docs + unit acceptance; not a gold table) |
| **Pilot source** | Yahoo Finance via **`yfinance`** / `edgar_warehouse.market.price_provider.PriceProvider` |
| **Layer** | **External Explore join** — not pure-SEC Agent-Grade features |
| **ADR 0001** | Unchanged — no price/mcap/PE inside Decision Feature vectors |

---

## 1. Why expand scope

EOD prices unblock valuation and price-aware outputs across most ER skills (see `assets/er-skills-unblocked-with-eod.md`), especially:

- initiating-coverage Task 3 (WACC, comps, DCF PT)  
- model-update PT refresh  
- idea-generation / sector multiples  
- earnings note valuation sections  

This product **documents and accepts** the market join as a first-class phase-1 capability without promoting Yahoo data into Gold MARKET tables (phase-2 optional).

---

## 2. Goals

1. Document **join contract**: ticker|CIK + `as_of` → close, mcap, beta (and related).  
2. Reuse **existing** `PriceProvider` + `wacc.py`.  
3. Define acceptance tests for sample universe.  
4. Keep Agent-Grade pure-SEC boundary (ERDP-06).  
5. Enable ER skill recipes for valuation without new paid vendors.

---

## 3. Non-goals

| Out | Notes |
|-----|--------|
| Gold `MARKET_PRICES` table in Snowflake | Phase-2 option only |
| Real-time / intraday | EOD only |
| Options / IV | Still External separate |
| Street ratings | Still External |
| Injecting prices into Subject Bundle features | Forbidden |

---

## 4. Contract (logical)

### 4.1 Join keys

| Key | Resolution |
|-----|------------|
| `ticker` | Primary for yfinance |
| `cik` | Resolve via `TICKER_REFERENCE` / MDM → primary ticker |
| `as_of` | ISO date; use last available session ≤ as_of |

### 4.2 Fields (minimum)

| Field | Source |
|-------|--------|
| `close` / `adj_close` | yfinance |
| `market_cap` | yfinance |
| `beta` | yfinance |
| `shares_outstanding` | yfinance or gold DERIVED shares (prefer gold for shares when present) |
| `currency` | USD for US pilot |

### 4.3 Derived with gold

| Output | Formula inputs |
|--------|----------------|
| Equity value | mcap |
| Enterprise value | mcap + total_debt − cash (gold DERIVED) |
| EV/EBITDA, P/E, EV/Sales | EV/price + gold earnings/EBITDA/rev |
| WACC | `wacc.py` + gold debt/tax + market Ke inputs |
| Upside to model PT | (PT − spot) / spot |

---

## 5. Agent usage rules

```text
Agent-Grade Decision Contract  →  pure-SEC only (no ERDP-07 fields)

Explore / research / ER valuation
  →  Gold fundamentals  ⋈  ERDP-07 PriceProvider(ticker, as_of)
  →  Label outputs as Explore; cite source_system=yahoo
```

---

## 6. Acceptance criteria

| ID | Criterion |
|----|-----------|
| **A07.1** | For sample universe ≥5 liquid US tickers, `get_price(ticker, as_of)` returns non-null close for a recent trading day. |
| **A07.2** | CIK→ticker→price path works for ≥5 MDM-tracked CIKs via TICKER_REFERENCE. |
| **A07.3** | `compute_wacc` succeeds for ≥1 CIK with gold debt + yfinance mcap/beta (or documented overrides). |
| **A07.4** | Docs state Explore-only; forbidden in pure-SEC feature vectors (lint/review). |
| **A07.5** | ER recipe docs: model-update PT table; initiation Task 3 multiples; idea value screen (platform docs home). |
| **A07.6** | Caching guidance documented (batch-safe; no unbounded Yahoo hammering). |

---

## 7. REQUIREMENTS IDs

See milestone REQUIREMENTS § ERDP-07.

---

## 8. Traceability

- `eod-price-source-decision.md`  
- `er-skills-unblocked-with-eod.md`  
- `models-on-gold-mdm-neo4j.md`  
- `edgar_warehouse/market/price_provider.py`, `wacc.py`  
- ERDP-06 / ADR 0001  

---

## 9. Implementation map (2026-07-24)

| Piece | Location |
|-------|----------|
| Join helpers | `edgar_warehouse/market/eod_join.py` |
| Price / beta / rf | `edgar_warehouse/market/price_provider.py` |
| WACC | `edgar_warehouse/market/wacc.py` |
| Consumer docs | `docs/er-market-eod-join.md` |
| Unit + opt-in live tests | `tests/unit/test_market_eod_join.py` (`ERDP07_LIVE=1`) |
| ER read map section | `assets/erdp-05-existing-surface-read-map.md` §9b |

*Spec version 1.1 — Explore join implemented; no Gold MARKET table.*
