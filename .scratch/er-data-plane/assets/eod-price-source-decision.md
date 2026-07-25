# EOD price source decision (pilot)

| Field | Value |
|-------|--------|
| **Decision date** | 2026-07-24 |
| **Choice** | **#1 — Yahoo Finance via `yfinance`** |
| **Status** | Pilot / External market join (not Gold MARKET product) |
| **Aligns with** | ERDP-06 (External only); ADR 0001 (no price in pure-SEC features) |
| **Platform hook** | `edgar_warehouse/market/price_provider.py` (already uses yfinance for close, mcap, beta) |

## What this unlocks

- WACC via `wacc.py` (mcap, beta + FRED rf + Damodaran ERP)
- EV / equity bridge, trading multiples, simple DCF market side
- ER valuation paths that join fundamentals (CIK/ticker + as_of) to External EOD

## Rules

1. Prices stay **External** — do not inject into `subject_features` or Agent-Grade pure-SEC vectors.  
2. Cache aggressively for batch jobs; do not hammer Yahoo per query.  
3. Production / client gold MARKET still requires a **paid** EOD vendor later if promoted to first-class gold.  
4. Confirm ToS before bulk load into shared Snowflake for commercial use.

## Alternatives (not selected for pilot)

| Rank | Source | When to reconsider |
|------|--------|--------------------|
| 2 | Stooq | Bulk historical CSV backfill |
| 3 | Alpha Vantage / Finnhub | Need formal API key + higher structure |

## Implementation note

**No implementation in this decision.** When building market join: reuse `PriceProvider`, join keys `ticker` or CIK (via TICKER_REFERENCE) + `as_of` date.
