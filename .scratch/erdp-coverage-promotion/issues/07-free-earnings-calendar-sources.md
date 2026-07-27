# 07 — Free authoritative earnings-calendar data sources

Type: research
Status: claimed
Blocked by:

## Question

`EARNINGS_CALENDAR` (ERDP-03) has only two implemented ingest paths today: `finnhub` (`parse_finnhub_earnings_calendar`/`fetch_finnhub_earnings_calendar`, `edgar_warehouse/explore/earnings_calendar.py:321-475`) — needs a commercial license not yet cleared — and `firm_manual` (manual CSV, works but can't scale to a coverage-universe-wide, every-trading-day need). The module docstring claims `yahoo` as a documented fallback, but **no `parse_yahoo_*`/`fetch_yahoo_*` function exists anywhere in the file** — it was never actually built.

Survey free, authoritative sources for forward-looking company earnings-report dates (not historical/reactive — the product needs *expected* dates, with session timing pre-market/after-close where available) that could realistically become a real ingest path:

1. **`yfinance`/Yahoo Finance specifically** — this platform already depends on `yfinance` for `ERDP-07` (`edgar_warehouse/market/eod_join.py`, `PriceProvider`), so if `yfinance`'s public API (e.g. `yf.Ticker(ticker).calendar` or equivalent) genuinely exposes next-earnings-date data, that's a zero-new-dependency path — verify this against `yfinance`'s actual current API (check the installed version's source/docs, not assumptions) and note any rate-limit/reliability caveats.
2. **Nasdaq's public earnings calendar** (api.nasdaq.com or similar) — verify whether it has a genuinely free, ToS-compliant public endpoint (not just a scrapeable webpage) and what data it returns.
3. **SEC itself** — is there any SEC-published forward-looking earnings-date signal (e.g. a company's own prior-quarter 8-K Item 2.02 filing pattern used to *predict* the next date, as opposed to sourcing an authoritative date)? Note clearly if this is prediction/inference rather than a real forward-calendar source, since that's a materially different reliability profile.
4. Any other genuinely free (no paid tier required to get *some* usable coverage), ToS-compliant source you find credible — cite official docs/pricing pages, not third-party blog claims.

For each candidate: does it require an API key/registration (free tier)? What are the actual ToS/rate-limit constraints (cite the source)? Does it return session timing (pre-market/after-close) or just a date? Is it query-per-ticker or bulk/calendar-wide? Recommend whether any candidate is realistically implementable as a real `source_system` value alongside `finnhub`/`firm_manual`, or whether none clear the bar and `firm_manual`-only promotion (deferred to ticket 05's own decision once this returns) is the honest fallback.

## Answer

(pending)
