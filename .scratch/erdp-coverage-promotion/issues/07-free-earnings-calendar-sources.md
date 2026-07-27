# 07 — Free authoritative earnings-calendar data sources

Type: research
Status: resolved
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

All primary-source research below was done against the repo's actual pinned `yfinance` version
(`uv.lock` resolves `yfinance>=0.2.40` in `pyproject.toml` to **`1.4.1`**), the real Alpha
Vantage docs page, a live test hit of `api.nasdaq.com`, and Nasdaq's/Yahoo's own
robots.txt/ToS text — not third-party blog claims.

### 1. `yfinance` 1.4.1 (already a dependency, ERDP-07)

Fetched the actual `1.4.1` tag source from GitHub (`ranaroussi/yfinance`) rather than trusting
docs pages (the Sphinx API-reference pages for `Ticker.calendar` / `Ticker.get_earnings_dates`
render via JS and returned only stub text over WebFetch — the source is the real primary
source here). There are **three** distinct earnings-date surfaces in this one version, with
materially different shapes:

**a) `Ticker.calendar` property** (`yfinance/scrapers/quote.py::_fetch_calendar`) — calls
Yahoo's `quoteSummary` endpoint (`modules=['calendarEvents']`) and returns a dict:
`Earnings Date` (list of `datetime.date` — **date only, no hour/session**), `Earnings
High/Low/Average`, `Revenue High/Low/Average`, `Dividend Date`, `Ex-Dividend Date`. Per-ticker
only. No session timing at all.

**b) `Ticker.get_earnings_dates(limit=12, offset=0)`** (`yfinance/base.py`) — in 1.4.1 this is
implemented by `_get_earnings_dates_using_scrape`, which does exactly what the name says:
`BeautifulSoup` + `pandas.read_html()` against the HTML `<table>` on
`https://finance.yahoo.com/calendar/earnings?symbol=X` — **literal webpage HTML scraping, not
a JSON API call**. The method's own docstring/comment on the deprecated JSON path
(`_get_earnings_dates_using_screener`, superseded but still present in the file) states
verbatim: *"In Summer 2025, Yahoo stopped updating the data at this endpoint. So reverting to
scraping HTML."* — i.e. the yfinance maintainers themselves had to abandon Yahoo's undocumented
JSON endpoint for this exact per-ticker use case and fall back to scraping a consumer webpage,
within roughly a year of today. The scraped table *does* carry an hour + timezone (parsed via
`'%B %d, %Y at %I %p'`, e.g. "October 30, 2025 at 4 PM EDT"), which could be heuristically
bucketed into pre/after-market, but there is no explicit BMO/AMC label. Per-ticker only,
`limit` capped at 100.

**c) `yfinance.Calendars().get_earnings_calendar()`** (`yfinance/calendars.py`) — the one
genuinely **bulk** surface: a date-range query (not per-ticker) against the same undocumented
Yahoo JSON endpoint (`{_QUERY1_URL_}/v1/finance/visualization`) that (b)'s deprecated path used
before Yahoo broke it. Requested fields include `ticker`, `companyshortname`,
`intradaymarketcap`, `eventname`, `startdatetime`, **`startdatetimetype`** (name strongly
suggests session/BMO-AMC info, but I could not independently confirm the actual label/values
from a live authenticated response, so treat as unconfirmed, not proven), `epsestimate`,
`epsactual`, `epssurprisepct`. Important scope caveat: `filter_most_active=True` by default —
unless a `market_cap` cutoff is supplied, this bulk call is scoped to Yahoo's ~200 "most
active" tickers, **not** an arbitrary coverage universe. It also hits the *same endpoint
family* the (b) docstring documents as having gone stale for the per-ticker case — whether the
bulk path is still being freshly updated is an open, unverified reliability question, not a
confirmed-safe path.

**Reliability/ToS risk (applies to all three):** yfinance is entirely an unofficial wrapper
around undocumented Yahoo endpoints; Yahoo retired its official public Finance API in 2017 and
never replaced it. Yahoo's own Terms of Service prohibit "robots, spiders, crawlers, scrapers,
or other automated means or interface not provided by us to access the Services or extract
data." Path (b) in the *currently pinned version* is explicit HTML scraping, which is squarely
inside that prohibited category. Note this is not a new risk introduced by this ticket — the
platform already accepted this exact risk class for EOD prices (`edgar_warehouse/market/eod_join.py`
already hardcodes `SOURCE_SYSTEM_YAHOO = "yahoo"`), so extending it to earnings dates is a
precedent-consistent decision, not virgin risk — but it should be made explicitly by whoever
resolves ticket 05, not smuggled in via the docstring's unbuilt `yahoo` fallback claim.

### 2. Nasdaq's earnings calendar

Live-tested today: `GET https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD` returns
HTTP 200 with no API key, JSON body, one call per date covering **all** companies reporting
that day (genuinely bulk/calendar-wide). Fields per row: `symbol`, `name`, `marketCap`,
`fiscalQuarterEnding`, `epsForecast`, `noOfEsts`, `lastYearRptDt`, `lastYearEPS`, and — real
finding — **`time`** with observed values `"time-pre-market"` / `"time-after-hours"` in
today's live response: genuine, explicit session timing, better than anything yfinance exposes.

However: this is an **internal, undocumented** endpoint that powers `nasdaq.com`'s own
earnings-calendar webpage. I found no official Nasdaq developer portal, API-key program, or
published terms specifically covering `api.nasdaq.com`. Direct primary-source check:
`https://api.nasdaq.com/robots.txt` returns *"This robots.txt file disallows all web crawlers
from indexing any pages in this API application"* with `Disallow: /` for the entire subdomain —
Nasdaq is explicitly signaling this surface is not meant for third-party discovery/access, even
though robots.txt technically governs crawling more than programmatic API consumption. There is
no confirmed rate limit (because there is no confirmed contract at all). This is the **least**
ToS-defensible of the free candidates found, despite having the best data shape (bulk + explicit
session timing).

### 3. SEC itself

None of SEC's documented public APIs (submissions.json, XBRL company-facts/company-concept/
frames, EDGAR full-text search) expose a forward-looking "next expected earnings date" field —
all of them are populated only after a filing lands, i.e. strictly historical/reactive, same as
this repo's own `EARNINGS_RELEASES.filing_date`. The only SEC-adjacent signal is **prediction,
not sourcing**: inferring next quarter's date from a company's own historical Item 2.02 8-K
filing cadence (e.g. "this company reports ~91 days after fiscal quarter-end, consistently").
This is a materially different reliability class from an authoritative calendar source — it is
a statistical estimate with no explicit session timing at all (8-Ks don't reliably encode
pre/post-market), it silently breaks whenever a company changes reporting cadence, IR practice,
or fiscal calendar, and it cannot be validated against an independent source without... an
independent source. It should not be modeled as a `source_system` value comparable to
`finnhub`/`firm_manual`/anything above — if implemented at all, it belongs in `status=estimated`
with materially lower confidence semantics than a vendor-sourced date.

### 4. Alpha Vantage `EARNINGS_CALENDAR` — the only clean official candidate

Official docs (`https://www.alphavantage.co/documentation/#earnings-calendar`), fetched
directly:

- `GET https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&horizon={3month|6month|12month}&apikey=KEY`
  — optional `symbol=` narrows to one ticker; **omitting `symbol` returns the full bulk list of
  every company's expected earnings in the horizon window in one call** — genuinely bulk,
  calendar-wide, and this is a first-party, documented, ToS-published API, not scraping or a
  reverse-engineered internal endpoint.
- Requires a free API key via self-serve signup (`alphavantage.co/support/#api-key`) — no cost
  for the baseline tier.
- Response is CSV. Standard published fields for this endpoint: `symbol`, `name`, `reportDate`,
  `fiscalDateEnding`, `estimate`, `currency` — **date only, no session/AM-PM field whatsoever.**
- Free-tier rate limit, confirmed from Alpha Vantage's own pricing page
  (`alphavantage.co/premium/`): **25 API requests per day** — a hard ceiling. This rules out any
  usage pattern that queries per-ticker across a coverage universe, but is workable for a
  once-daily (or few-times-daily) *bulk* pull (omit `symbol`), since one bulk call returns the
  whole market's near-term calendar.

### Recommendation to ticket 05

No single free candidate clears **all three** bars this ticket set (bulk/scalable + session
timing + genuinely ToS-clean) at once:

| Candidate | Bulk? | Session timing? | ToS-clean/official? |
|---|---|---|---|
| yfinance `Ticker.calendar` | No (per-ticker) | No (date only) | No (unofficial Yahoo wrapper) |
| yfinance `get_earnings_dates` | No (per-ticker) | Weak (hour, no BMO/AMC label) | No (explicit HTML scraping in the pinned version) |
| yfinance `Calendars.get_earnings_calendar` | Partial (date-range, defaults to ~200 most-active only) | Unconfirmed (`startdatetimetype` field requested, values unverified) | No (same unofficial-endpoint family flagged elsewhere in yfinance's own code as having gone stale) |
| Nasdaq `api.nasdaq.com` | Yes (full day, all tickers) | **Yes** (`time-pre-market`/`time-after-hours`, confirmed live) | No (undocumented internal endpoint; `robots.txt` disallows the whole subdomain) |
| SEC 8-K Item 2.02 cadence | N/A | No | N/A — this is prediction, not sourcing; different reliability class entirely |
| **Alpha Vantage `EARNINGS_CALENDAR`** | **Yes** (bulk mode, one call/day) | **No** (date only) | **Yes** — documented, first-party, published free tier |

**Decisive recommendation:** if the bar is "genuinely free + ToS-compliant + realistically
implementable as a new `source_system`," **Alpha Vantage is the only candidate that clears it**,
and it should be added as a new `source_system` (e.g. `"alphavantage"`) using **bulk mode only**
(no `symbol=`, respecting the 25-req/day free-tier ceiling by pulling the full calendar once or
a few times per day, not per-ticker) — it would map to `session="unknown"` for every row, since
the source has no timing field at all; that's a legitimate value already in this module's
`SESSIONS` enum, not a workaround. This closes the "can't scale to a coverage-universe-wide,
every-trading-day need" gap that `firm_manual` can't, without the `finnhub` license gate, at the
cost of losing session timing entirely.

If session timing is treated as a hard requirement rather than nice-to-have, **no free,
ToS-clean candidate provides it** — Nasdaq's endpoint has it but fails the ToS bar this ticket
was explicitly scoped to test for; yfinance's HTML-scrape path has a weaker, unlabeled version
of it but is explicit scraping under a ToS that forbids it. That gap should be named plainly to
whoever resolves ticket 05, not papered over by picking the best-looking field name.

Separately, regardless of which source(s) ticket 05 picks: the module docstring's claim of an
existing `yahoo` fallback is inaccurate today (confirmed — no `parse_yahoo_*`/`fetch_yahoo_*`
function exists in `earnings_calendar.py`) and should be corrected to reflect reality (either
remove the claim, or replace it with an explicit build task if `yahoo` is chosen), since the
platform's own EOD-price code already sets a `"yahoo"` `source_system` precedent
(`edgar_warehouse/market/eod_join.py:17`) that a resolver might reasonably want to extend
consciously rather than assume already covers this product.

**Sources consulted (primary):**
- `https://github.com/ranaroussi/yfinance` — tag `1.4.1`: `yfinance/base.py`,
  `yfinance/scrapers/quote.py`, `yfinance/calendars.py`, `CHANGELOG.rst`
- `https://www.alphavantage.co/documentation/#earnings-calendar` and
  `https://www.alphavantage.co/premium/` (free-tier rate limit)
- `https://api.nasdaq.com/api/calendar/earnings?date=2026-07-28` (live test, 2026-07-27) and
  `https://api.nasdaq.com/robots.txt`
- Yahoo Finance Terms of Service (automated-access prohibition, widely cited/confirmed across
  independent secondary sources; Yahoo's official public Finance API was retired in 2017)
