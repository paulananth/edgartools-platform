# Free data sources: Consensus · Calendar · Transcript

**Date:** 2026-07-25  
**Products:** ERDP-01, ERDP-03, ERDP-04  
**Caveat:** Free tiers and ToS change; re-check commercial use / redistribution before loading into Snowflake gold.

Related: `free-data-sources-erdp-01-04.md` (includes guidance/SEC), `eod-price-source-decision.md` (yfinance for prices).

---

## Recommended free pilot stack

| Product | Rank-1 free source | `source_system` | Rank-2 | Avoid as sole SoR |
|---------|-------------------|-----------------|--------|-------------------|
| **Consensus (01)** | **Yahoo / yfinance** estimates | `yahoo` | FMP free (analyst estimates) | Treating free data as IBES |
| **Calendar (03)** | **Finnhub free** earnings calendar | `finnhub` | Yahoo calendar / `get_earnings_dates` | Relying on exact HH:MM free |
| **Transcript (04)** | **Company IR URL** (+ optional S3 copy) | `ir_website` | firm_manual file drop | Seeking Alpha bulk scrape |

**Same vendor convenience:** FMP free can touch calendar + some estimates + transcript *endpoints*, but free **250 calls/day** and feature gating make it a backup, not a full-universe production SoR.

---

## 1. Consensus estimates (ERDP-01)

### Free / freemium options

| Source | Access | What you get | Limits |
|--------|--------|--------------|--------|
| **Yahoo Finance** | Web + **`yfinance`** (`Ticker.earnings_estimate`, analysis/estimates, related) | EPS & revenue estimates, growth, often analyst counts; sometimes high/low | Unofficial; breakable; weak multi-`as_of` history; ToS for redistribution |
| **FMP** | Free API key | Analyst / financial estimates; actual vs estimate on earnings endpoints | ~**250 calls/day** free; some estimate depth may be paid; not IBES |
| **Finnhub** | Free API key | EPS surprises (limited quarters free); full multi-year estimates often **paid** | Free estimates thin; calendar stronger than estimates on free |
| **Estimize** | Web / paid API | Crowdsourced EPS & revenue consensus | Free via **give-to-get**; not sell-side Street consensus |
| **Alpha Vantage** | Free API key | Limited earnings-related series | Low daily cap; uneven for consensus packs |

### Schema fit (`CONSENSUS_ESTIMATES`)

| Field | Free path quality |
|-------|-------------------|
| `metric` revenue / eps_diluted | Good (Yahoo/FMP) |
| `estimate_value`, high/low | Fair |
| `statistic` mean / n_analysts | Fair |
| **`as_of` history** | **Poor free** — usually “latest” only |
| Street IBES quality | **No free equivalent** |

### Pilot recommendation

```text
source_system = yahoo   # or fmp
primary metrics       = revenue, eps_diluted
acceptance A01.2      = best-effort / waive deep as_of history on free pilot
firm_manual           = CSV fallback for demo names
```

---

## 2. Earnings calendar (ERDP-03)

### Free / freemium options

| Source | Access | What you get | Limits |
|--------|--------|--------------|--------|
| **Finnhub** `/calendar/earnings` | Free API | Date, **hour** `bmo`/`amc`/`dmh`, EPS estimate/actual | Free: ~**1 month** history + live updates (US); **personal-use** terms often; 60 calls/min free |
| **Yahoo Finance** calendar | Web + scrapers / `yfinance` `get_earnings_dates`, community scrapers | Date, BMO/AMC, EPS est/actual, surprise | Scrapers fragile; yfinance calendar endpoints break often |
| **FMP** earnings calendar | Free API | Date range calendar; est/actual; time often **bmo/amc** only | Free call/day cap; time field historically unstable |
| **EODHD** calendar | Free trial / limited free | report_date, before/after market, estimate | Free tier small |
| **API Ninjas** | Free quota | before/during/after market | Quota |
| **Company IR** | Manual | Confirmed date/time | Gold quality; not bulk |
| **firm_manual** | CSV | Full control | Ops cost |

### Schema fit (`EARNINGS_CALENDAR`)

| Field | Free path quality |
|-------|-------------------|
| `expected_date` | **Good** (Finnhub, Yahoo, FMP) |
| `session` pre/after | **Good** as BMO→`pre_market`, AMC→`after_close` |
| `expected_time` HH:MM | **Poor** — usually missing free |
| `status` estimated/confirmed | Weak; often implied |

### Pilot recommendation

```text
source_system = finnhub          # structured API + bmo/amc
fallback      = yahoo / firm_manual
expected_time = null allowed
session map   = bmo→pre_market, amc→after_close, dmh→during_session
```

**Note:** Finnhub free license is often **personal use** — check before commercial gold warehouse.

---

## 3. Transcripts (ERDP-04)

### Free / freemium options

| Source | Access | What you get | Limits |
|--------|--------|--------------|--------|
| **Company IR websites** | Public HTTPS | Official PDF/HTML/text | **Best free legitimacy**; no bulk API; URL rot |
| **firm_manual** | S3 drop | Full control of text | Best for pilot quality |
| **SEC EDGAR** | Public | Occasional exhibits / attachments | Incomplete coverage |
| **Seeking Alpha** | Free web | Large transcript library | **No free bulk API**; scrape = ToS risk |
| **FMP** transcript APIs | Free/paid tiers | Structured transcripts | Free plan may list availability; full text often paid / bandwidth limited |
| **API Ninjas** | Free tier restricted | Historical transcripts | **Commercial use not free** |
| **Finnhub** | Mostly paid for deep transcript history | Long history on paid | Free not for bulk transcripts |

### Schema fit (`TRANSCRIPT_EVENTS` + object store)

| Approach | Free path |
|----------|-----------|
| Pointer-only `storage_uri=https://ir...` | **Yes** — IR |
| Platform S3 copy + sha256 | **Yes** — download IR or firm file |
| Full-universe automated free API | **No reliable free option** |

### Pilot recommendation

```text
source_system = ir_website | firm_manual
universe      = small pilot CIK list (not all EDGAR)
storage       = prefer S3 copy for key names; pointer OK for MVP
do not        = bulk scrape Seeking Alpha into gold
```

---

## 4. Unified free pilot matrix

| Need | Best free source | API quality | Commercial gold risk |
|------|------------------|-------------|----------------------|
| Consensus | Yahoo / FMP | Medium | Medium–high (ToS) |
| Calendar | Finnhub free | Good for dates/session | Medium (license) |
| Transcript | IR + firm_manual | High legitimacy, low scale | Low if IR/firm only |
| Prices (related) | yfinance (already chosen) | Medium | Medium |

### One-stack option (simpler ops, thinner coverage)

| All three | **FMP free** for calendar + estimates + try transcripts |
|-----------|--------------------------------------------------------|
| Cap | 250 calls/day, feature gating |
| Use | Small tracked universe only |

### Best-quality free stack (recommended)

```text
Calendar   → Finnhub (or Yahoo)
Consensus  → Yahoo / yfinance (same stack as EOD) or FMP
Transcript → IR URL + optional S3 (firm_manual for demos)
Prices     → yfinance (ERDP-07)
Guidance   → SEC (ERDP-02) — not free vendor
```

---

## 5. Map to ERDP `source_system` values

| source_system | Products |
|---------------|----------|
| `yahoo` | Consensus, calendar (fragile) |
| `finnhub` | Calendar (best free API fit) |
| `fmp` | Consensus, calendar, transcript trial |
| `ir_website` | Transcript pointer |
| `firm_manual` | All three (CSV/files) |
| `estimize` | Consensus alternative (crowdsourced) |

---

## 6. What free cannot do well

1. **IBES-grade consensus** with deep revision history (`as_of` panels).  
2. **Exact call clock times** on calendar for full universe.  
3. **Bulk transcripts** with clean license and API.  
4. Guaranteeing **commercial redistribution** into multi-tenant Snowflake.

For client-facing production ER, budget **one paid** consensus+calendar vendor and a transcript API or firm IR pipeline.

---

## 7. Pilot decisions (**locked** 2026-07-25)

| Product | Primary `source_system` | Fallback | Spec |
|---------|-------------------------|----------|------|
| ERDP-01 Consensus | **`yahoo`** | `firm_manual` (optional `fmp`) | `specs/ERDP-01-consensus-estimates.md` §11.1 |
| ERDP-03 Calendar | **`finnhub`** | `yahoo` / `firm_manual` | `specs/ERDP-03-earnings-calendar.md` §11.1 |
| ERDP-04 Transcript | **`ir_website`** + **`firm_manual`** | — (small pilot list) | `specs/ERDP-04-transcript-mvp.md` §10.1 |
| ERDP-07 EOD prices | **`yahoo` / yfinance** | — | `specs/ERDP-07-market-eod-join.md` |
| ERDP-02 Guidance | **`sec_*`** (not free vendor) | `firm_manual` | `specs/ERDP-02-guidance-facts.md` |

---

*Research snapshot 2026-07-25; pilot sources locked. Verify free-tier limits and licenses before implement.*
