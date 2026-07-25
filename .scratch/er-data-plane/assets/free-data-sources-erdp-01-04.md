# Free / low-cost data sources for ERDP-01…04

**Date:** 2026-07-24  
**Purpose:** Source options for phase-1 gold products (no paid FactSet/Bloomberg/CapIQ required for a pilot).  
**Caveat:** “Free” tiers change; always re-check ToS (commercial use, redistribution, rate limits) before production.

---

## Summary recommendation (pilot)

| Product | Best free-aligned path | Institutional quality? |
|---------|------------------------|------------------------|
| **ERDP-01 Consensus** | **Yahoo Finance / yfinance** EPS & revenue estimates + history; optional **FMP free tier** for actual-vs-estimate | Lower than Street terminals; OK for demo / non-client |
| **ERDP-02 Guidance** | **SEC EDGAR** (platform 8-K/10-Q parse) — already in architecture | High for GAAP narrative; extraction hard |
| **ERDP-03 Calendar** | **Yahoo Finance calendar** (scrape/community) or **Finnhub free** earnings calendar; **FMP free** calendar | Medium; times often BMO/AMC only |
| **ERDP-04 Transcript** | **Company IR** + **Seeking Alpha** (web, not clean API); **SEC** rare full transcripts; paid APIs for scale | Free = messy / ToS-sensitive |

---

## ERDP-01 — Consensus estimates

### Free / freemium options

| Source | What you get | Limits / notes |
|--------|--------------|----------------|
| **Yahoo Finance** (via `yfinance` / unofficial) | Forward & trailing EPS/revenue estimates, growth, often # of analysts | Unofficial API risk; rate limits; not redistribution license; good prototype |
| **Financial Modeling Prep (FMP)** free plan | Analyst estimates / financial estimates endpoints; actual vs estimate on some earnings endpoints | ~250 calls/day free (varies); commercial ToS check; not IBES |
| **Finnhub** free | Some estimate endpoints; many estimate products **premium/enterprise** | Free tier thin for full consensus history |
| **EODHD** free trial | Calendar + estimate fields on some plans | Free tier limited |
| **Estimize** | Crowdsourced EPS/revenue consensus | Free via **give-to-get** estimates or paid API; not sell-side Street consensus |
| **Alpha Vantage** | Limited earnings/estimate-related endpoints on free | Rate-limited; quality uneven |

### Not free (reference only)

FactSet, Bloomberg, CapIQ, Refinitiv — institutional Street consensus (as_of, revisions).

### Fit to schema `CONSENSUS_ESTIMATES`

| Schema field | Free path typically provides |
|--------------|------------------------------|
| `metric` | EPS, revenue (sometimes limited set) |
| `estimate_value` / high/low | Often avg; high/low sometimes |
| `statistic` | mean; `n_analysts` sometimes |
| `as_of` | **Weak** — often “current” only; history of as_of hard free |
| `source_system` | `yahoo`, `fmp`, `estimize`, … |

**Recommendation:** Pilot with `source_system=yahoo` or `fmp`; document that **historical as_of depth** may not meet A01.2 without paid history.

---

## ERDP-02 — Guidance values

### Free / first-party options

| Source | What you get | Limits / notes |
|--------|--------------|----------------|
| **SEC EDGAR 8-K / 10-Q / 10-K** | Company-issued guidance in text/HTML | **Preferred** in REQUIREMENTS; free; needs NLP/parse |
| **Platform `EARNINGS_RELEASES`** | Today: `has_guidance` **boolean only** | Extend parser for numeric low/mid/high |
| **Press releases on IR** | Same narrative as 8-K often | Free; scrape/ToS |
| **Yahoo / FMP** | Sometimes “guidance” fields on earnings pages | Unreliable / incomplete free |

### Fit to schema `GUIDANCE_FACTS`

Best free SoR is **SEC**, not Street vendors. Aligns with ERDP-02-05 (prefer SEC parse).

**Recommendation:** Do **not** depend on free consensus APIs for guidance; invest in **SEC text extraction** (or firm_manual CSV for pilot names).

---

## ERDP-03 — Earnings calendar

### Free / freemium options

| Source | What you get | Limits / notes |
|--------|--------------|----------------|
| **Yahoo Finance earnings calendar** | Date, BMO/AMC, EPS estimate, actual, surprise | Free web; scrapers exist (`yahoo_earnings_calendar`); fragile |
| **Finnhub** `earnings-calendar` | Date, hour `bmo`/`amc`/`dmh`, EPS estimate/actual | Free tier with limits (e.g. short history windows) |
| **FMP** earnings calendar | Date, EPS estimate/actual; **time field removed** for instability | Free plan access claimed; BMO/AMC via other endpoints evolving |
| **EODHD** calendar | `report_date`, `before_after_market`, estimate/actual | Free trial / limited free |
| **API Ninjas** earnings calendar | before/during/after market | Free quota |
| **Nasdaq / exchange calendars** | Partial lists | Not full universe |
| **Company IR** | Confirmed date/time | Gold standard; not bulk free |

### Fit to schema `EARNINGS_CALENDAR`

| Schema field | Free path |
|--------------|-----------|
| `expected_date` | Yes (Yahoo/Finnhub/FMP) |
| `session` pre/after | Often BMO/AMC only |
| `expected_time` HH:MM | **Rare free** — usually missing |
| `status` estimated/confirmed | Weak; often implied |

**Recommendation:** Pilot `source_system=finnhub` or `yahoo`; map BMO→`pre_market`, AMC→`after_close`; accept `expected_time` null for free tier.

---

## ERDP-04 — Transcripts

### Free / freemium options

| Source | What you get | Limits / notes |
|--------|--------------|----------------|
| **Company IR websites** | Official PDF/HTML/audio | Free; per-issuer scrape; highest legitimacy |
| **Seeking Alpha** | Large free transcript library (web) | **Not a clean free bulk API**; ToS/scraping risk |
| **SEC EDGAR** | Occasional transcript exhibits / 8-K attachments | Incomplete; not standard for all issuers |
| **FMP** transcript endpoints | API transcripts | Free tier may include latest-list; full text often paid |
| **API Ninjas** transcripts | Historical transcripts | **Commercial use restricted on free** |
| **Finnhub** transcripts | Available; often premium |
| **Academic / WRDS** | CapIQ transcripts | Institutional access, not “free public API” |

### Fit to schema `TRANSCRIPT_EVENTS`

| Approach | How |
|----------|-----|
| **MVP free** | Gold pointer `storage_uri` → IR URL or S3 copy after manual/curated download for pilot CIKs |
| **Scale free-ish** | IR crawler + SHA256; heavy ops |
| **API freemium** | FMP/others for prototype; check redistribution |

**Recommendation:** Phase-1 free path = **firm-curated or IR URL pointers** for a small universe; do not promise full-universe free transcripts.

---

## Cross-walk to ERDP source_system values

| source_system | Products | License note |
|---------------|----------|--------------|
| `sec_8k` / `sec_10q` / `sec_10k` | Guidance (primary) | Public domain SEC |
| `yahoo` | Consensus, calendar | Unofficial / ToS |
| `fmp` | Consensus, calendar, transcript trial | Free tier limits |
| `finnhub` | Calendar (+ limited estimates) | Free tier limits |
| `firm_manual` | All | Your CSV/S3 drop |
| `ir_website` | Transcript pointer | Per-company |
| `estimize` | Consensus alternative | Crowdsourced ≠ Street |

---

## Suggested pilot stack (free-first)

```text
ERDP-02 Guidance     →  SEC (edgartools-platform parse)     [free, preferred]
ERDP-03 Calendar     →  Finnhub free OR Yahoo scrape        [free, fragile]
ERDP-01 Consensus    →  Yahoo/yfinance OR FMP free          [free, not IBES]
ERDP-04 Transcript   →  IR URL + optional S3 copy for N CIKs [free, not scale]
ERDP-06 Market       →  yfinance (already in market/)       [free, External]
```

**Production / client-grade:** budget for one commercial consensus + calendar + transcript vendor; keep schema `source_system` multi-source.

---

## Risks if free-only

1. **No stable as_of history** for consensus (fails strict A01.2).  
2. **Calendar times** incomplete (A03 session/time).  
3. **Transcript bulk** ToS/scraping risk.  
4. **Redistribution** into Snowflake gold may violate freemium ToS — legal review required.  
5. **Quality** not comparable to IBES/Street.

---

## Next planning step (no implement)

Record decisions in a short **Source matrix** under `.scratch/er-data-plane/`:

| ERDP | Pilot source_system | Production intent |
|------|---------------------|-------------------|
| 01 | ? | ? |
| 02 | sec_* | sec_* |
| 03 | ? | ? |
| 04 | ir_website / firm_manual | ? |

---

*Research snapshot 2026-07-24; re-verify free tiers and commercial-use clauses before build.*
