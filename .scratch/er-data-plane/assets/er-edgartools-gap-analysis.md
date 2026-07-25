# Gap analysis: ER skill data needs vs edgartools-platform (Gold / MDM / Neo4j)

**Date:** 2026-07-24  
**Sources:**  
- ER skills: `financial-services/plugins/vertical-plugins/equity-research/skills/`  
- Platform: `edgartools-platform` (`docs/data-architecture.md`, `gold_schemas.yaml`, MDM, Neo4j Snowflake graph, subject-bundle)

---

## 1. Executive summary

**edgartools-platform is strong on SEC-native issuer data** (identity, filings, XBRL financials, derived statements/margins, 8-K earnings snapshots, ownership, 13F, executives, auditor/parent graph). That covers a large share of **model build / initiation fundamentals / post-print actuals**.

**It does not currently expose a complete ER desk data plane.** Material **gaps** vs the nine ER skills:

| Priority | Gap theme | Blocks |
|----------|-----------|--------|
| **P0** | Street **consensus** (rev/EPS/segments, as-of) | earnings-preview, earnings-analysis beat/miss, morning-note |
| **P0** | **Transcripts** + full earnings narrative text as structured product | earnings-analysis phases 1–4, initiation research depth |
| **P0** | **Forward guidance values** (only `has_guidance` boolean on earnings release) | model-update, preview, earnings note |
| **P1** | **Market prices, shares for mcap, beta, options/implied move** (market module exists but is **yfinance/FRED optional**, not Gold/MDM/Neo4j product) | PT, EV multiples, trading setup, WACC |
| **P1** | **Earnings calendar** (date/time pre/post) as first-class gold | catalyst-calendar, preview |
| **P1** | Segment/product **revenue breakdown** for model (XBRL segment field exists but not a product/geo model table) | initiating-coverage Task 2 revenue model |
| **P2** | Peer **comps pack** (ready-made peer set + multiples as-of) | valuation, sector-overview |
| **P2** | Sell-side **ratings / PT history** | morning-note, thesis |
| **P2** | Macro calendar / non-SEC events | catalyst-calendar |
| **P3** | Analyst workflow state (thesis, coverage book, internal model path) | thesis-tracker, model-update — **out of platform scope by design** |

**Best platform fit today:** **initiating-coverage Tasks 1–2** (identity + multi-year financials + filings) and **model-update actuals plug** from `SEC_FINANCIAL_DERIVED` / `EARNINGS_RELEASE` — if you add consensus + price + guidance values externally.

---

## 2. Platform surfaces (what is “exposed”)

```text
SEC EDGAR → bronze → silver → gold Parquet / Snowflake EDGARTOOLS_GOLD
                         ↘ MDM (company, person, security, fund, adviser, audit_firm)
                              → relationship instances
                              → Snowflake GRAPH_NODES / GRAPH_EDGES (Neo4j Graph Analytics)
                         ↘ Subject Bundle / Feature Screen (decision contract)
```

### 2.1 Gold (warehouse + Snowflake `EDGARTOOLS_GOLD`)

| Product area | Tables / schemas | ER-relevant data points |
|--------------|------------------|-------------------------|
| Identity | `dim_company` / `COMPANY`, `TICKER_REFERENCE` | CIK, entity_name, SIC, FYE, ticker, exchange |
| Filings | `dim_filing`, `FILING_ACTIVITY`, `FILING_DETAIL` | form, accession, filing/report dates, XBRL flag |
| Financial facts | `SEC_FINANCIAL_FACT` / `financial_facts` | XBRL concept, value, unit, fiscal_year/period, period_end, **segment** |
| Derived P&L/BS/CF | `SEC_FINANCIAL_DERIVED` / `financial_derived` | revenue, GP, EBITDA, EBIT, NI, eps_diluted, assets/liab/equity, cash, debt, AR, inventory, SG&A, RE, D&A, PP&E, shares, OCF, capex, **FCF**, gross/ebitda/net margins, ROIC/ROE/ROA |
| Earnings 8-K | `EARNINGS_RELEASE` / `fact_earnings_release` | filing_date, FY/FQ, period_end, **revenue_gaap, NI_gaap, eps_gaap_diluted**, has_non_gaap, **has_guidance** (bool only) |
| Executives | `EXECUTIVE_RECORD` | name, role, salary/bonus/stock/option/total pay |
| Accounting forensics | `ACCOUNTING_FLAG` | auditor, PCAOB, Beneish/Altman/Piotroski-type scores |
| Ownership | ownership activity/holdings facts | Form 3/4/5 txns, shares, price, codes |
| 13F | `SEC_THIRTEENF_HOLDING` / institutional holdings | CUSIP, issuer, shares, market value, voting |
| ADV | offices, disclosures, private funds | Adviser/AUM (manager, not pure equity coverage) |

**Optional market helpers (not gold product):**  
`edgar_warehouse/market/price_provider.py` (yfinance, FRED DGS10, Damodaran ERP), `wacc.py` — for WACC/EV, **not** published as Gold/MDM/Neo4j tables.

### 2.2 MDM

| Entity | Key attributes | ER use |
|--------|----------------|--------|
| **company** | CIK, canonical name, ticker/exchange, tracking, parent link | Coverage universe, resolve ticker→CIK |
| **person** | Names, owner CIK, officer/director flags | Management / insider context |
| **security** | Title, issuer, CUSIP/class | Holdings, security identity |
| **adviser / fund / audit_firm** | ADV & audit domain | Secondary for pure ER; useful for ownership/audit narrative |

**Relationships** (graph-ready instances), including:  
`IS_INSIDER`, `HOLDS`, `COMPANY_HOLDS`, `ISSUED_BY`, `HAS_PARENT_COMPANY`, `MANAGES_FUND`, `EMPLOYED_BY`, `AUDITED_BY`, `INSTITUTIONAL_HOLDS`, …

### 2.3 Neo4j (Snowflake-hosted graph analytics)

| Surface | Content |
|---------|---------|
| `GRAPH_NODES` | NODEID, LABEL, PROPERTIES from MDM entities |
| `GRAPH_EDGES` | EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, PROPERTIES |
| Source mirror | MDM_COMPANY, PERSON, SECURITY, FUND, ADVISER, RELATIONSHIP_* |

**Subject Bundle Read (issuer)** stitches graph + gold for agents:

- insiders, employment (+ proxy pay), holders_of_subject (13F), subject 13F book, auditor, parent, **subject_features** (pure-SEC feature vector), ADV N/A for pure issuers  
- Explicitly **no market prices / PE / mcap** in pure-SEC features (ADR 0001)

---

## 3. ER skill data requirements → coverage matrix

Legend: **Full** = first-class gold/mdm/neo4j · **Partial** = some fields or optional market module · **Gap** = not exposed · **N/A** = skill-local / human process

### 3.1 Identity & universe

| Data point | ER skills | Gold | MDM | Neo4j/Bundle |
|------------|-----------|:----:|:---:|:------------:|
| Ticker → CIK | all | Full (`TICKER_REFERENCE`) | Full (`mdm_company`) | via company nodes |
| Company name, SIC, FYE | initiation, sector | Full | Full | Partial props |
| Coverage universe list | calendar, morning, ideas | Partial (tracked CIKs) | Full tracking | Decision universe |
| Exchange | comps, trading | Full | Full | Partial |

### 3.2 Filings & documents

| Data point | ER skills | Gold | MDM | Neo4j/Bundle |
|------------|-----------|:----:|:---:|:------------:|
| 10-K / 10-Q metadata | initiation, earnings, model | Full filing dims/facts | source refs | filing activity |
| Accession, filing/report dates | all product skills | Full | — | — |
| Primary document / attachments bytes | research, earnings | Bronze/S3 (not gold table) | — | — |
| Normalized filing **text** | research narrative | Silver `sec_filing_text` (backfill path) | — | — |
| **Earnings call transcript** | earnings-analysis | **Gap** | **Gap** | **Gap** |
| IR deck / supplemental | earnings-analysis | **Gap** | **Gap** | **Gap** |

### 3.3 Financial statements & model inputs

| Data point | ER skills | Gold | MDM | Neo4j/Bundle |
|------------|-----------|:----:|:---:|:------------:|
| Multi-year IS/BS/CF metrics | initiation T2, model-update | **Full** derived | — | subject_features (as-of) |
| Revenue, EBITDA, NI, EPS | earnings, model, valuation | Full | — | features |
| Cash, debt, shares | model, DCF | Full | — | features |
| FCF, OCF, capex | DCF, model | Full | — | features |
| Margins, ROIC/ROE/ROA | model, notes | Full | — | features |
| Full XBRL concept line items | deep model | Full facts | — | — |
| Product / geo revenue model (20–30 rows) | initiation T2 | **Partial** (segment string on facts; no curated product/geo model) | **Gap** | **Gap** |
| R&D / S&M headcount builds | initiation T2 | **Gap** (may exist as raw XBRL concepts only) | **Gap** | **Gap** |
| Bull/base/bear scenario store | initiation, preview | **Gap** (compute-only) | **Gap** | **Gap** |

### 3.4 Earnings event & estimates

| Data point | ER skills | Gold | MDM | Neo4j/Bundle |
|------------|-----------|:----:|:---:|:------------:|
| 8-K GAAP rev/NI/EPS snapshot | earnings-analysis, morning | Full `EARNINGS_RELEASE` | — | — |
| Non-GAAP metrics (values) | earnings note | **Partial** (`has_non_gaap` only) | **Gap** | **Gap** |
| Guidance **values** | preview, model-update | **Gap** (`has_guidance` only) | **Gap** | **Gap** |
| **Consensus** rev/EPS/segments + as-of | preview, earnings, morning | **Gap** | **Gap** | **Gap** |
| Whisper / options implied move | preview | **Gap** | **Gap** | **Gap** |
| Earnings **date & time** (pre/post) | calendar, preview | **Gap** as calendar product (filing date ≠ scheduled print time) | **Gap** | **Gap** |
| Prior-quarter guidance history | earnings-analysis | **Gap** | **Gap** | **Gap** |

### 3.5 Valuation / market

| Data point | ER skills | Gold | MDM | Neo4j/Bundle |
|------------|-----------|:----:|:---:|:------------:|
| Close price, market cap | model-update PT, comps | **Partial** (`market/` yfinance; not gold) | **Gap** | Explicitly excluded from pure-SEC features |
| Beta, ERP, rf (WACC) | initiation DCF | Partial (wacc.py + price_provider) | **Gap** | **Gap** |
| Peer set + trading multiples | initiation T3, sector | **Gap** as pack | Partial identity only | Partial relationships |
| Historical multiples series | charts | **Gap** | **Gap** | **Gap** |
| Target PT / rating (Street) | morning, thesis | **Gap** | **Gap** | **Gap** |

### 3.6 Qualitative / franchise ER

| Data point | ER skills | Gold | MDM | Neo4j/Bundle |
|------------|-----------|:----:|:---:|:------------:|
| Management bios | initiation T1 | Partial (exec names + pay) | person entities | employment edges |
| Competitive set | sector, initiation | **Gap** | **Gap** | **Gap** (no industry graph) |
| TAM / industry structure | sector | **Gap** | **Gap** | **Gap** |
| Insider transactions | idea screens, notes | Full ownership gold | IS_INSIDER | Bundle insiders |
| Institutional holders | idea, thesis | Full 13F | INSTITUTIONAL_HOLDS | holders_of_subject |
| Parent / sub structure | research | subsidiary evidence | HAS_PARENT | has_parent section |
| Auditor | research/risk | accounting flags | AUDITED_BY | auditor section |

### 3.7 Workflow / non-market data

| Data point | ER skills | Platform |
|------------|-----------|----------|
| Existing Excel model path | model-update | **N/A** — user workspace |
| Thesis pillars / conviction | thesis-tracker | **N/A** — firm system |
| Internal rating / PT | morning, thesis | **N/A** unless you store elsewhere |
| Macro event calendar | catalyst-calendar | **Gap** |

---

## 4. Skill-by-skill readiness (platform as primary SEC source)

| ER skill | Platform can supply today | Still need outside platform |
|----------|---------------------------|-----------------------------|
| **initiating-coverage T1** | Filings metadata, text (if projected), execs, ownership, parent, auditor, financial history for facts | Industry/TAM, competitors, full narrative research, non-SEC sources |
| **initiating-coverage T2** | Multi-year derived financials, many XBRL line items, shares/debt/cash/FCF | Curated product/geo revenue model, headcount/unit economics, scenario assumptions |
| **initiating-coverage T3** | UFCF inputs, debt/cash/shares; optional WACC helpers via market module | Live prices/mcap/beta in productized form; peer comps pack; Street multiples |
| **model-update** | Actuals from derived + earnings_release | Consensus, guidance **values**, price for PT, existing model file |
| **earnings-analysis** | GAAP actuals snapshot, filings links, financial history for charts | Transcript, consensus, full release narrative, IR deck, non-GAAP detail |
| **earnings-preview** | Prior financials, fiscal calendar rough from filings | Consensus, scheduled print time, guidance, options |
| **morning-note** | Overnight Form 8-K/4 filings via daily index/filings | Consensus vs actual, ratings, non-SEC news wire |
| **catalyst-calendar** | Filing dates (reactive), some corporate events via forms | Forward earnings calendar, conferences, macro |
| **thesis-tracker** | New SEC data points (earnings, 13F, Form 4) as “evidence” | Thesis structure, PT policy, conviction |
| **idea-generation** | Screens on pure-SEC features, ownership, 13F, accounting flags | Price/value screens, consensus revisions, short interest |
| **sector-overview** | Multi-issuer financials + tickers for a SIC slice | Industry research, peer narrative, market structure |

---

## 5. Recommended platform extensions (to close ER gaps)

Ordered by ER impact:

| # | Extension | Target surface | Unlocks |
|---|-----------|----------------|---------|
| 1 | **Consensus estimates table** (provider-agnostic schema: ticker, period, metric, value, as_of, source) | Gold (+ optional MDM security link) | preview, earnings, morning |
| 2 | **Guidance facts** (metric, period, low/mid/high, as_of, accession) | Gold from 8-K parser enrichment | model-update, notes |
| 3 | **Earnings calendar** (expected date, time, confirmed vs estimated) | Gold | calendar, preview |
| 4 | **Transcript store** (accession or event_id, speaker, text, URL) | Bronze→silver→gold or object store + gold pointer | earnings-analysis |
| 5 | **Productize market layer** into gold: daily close, mcap, beta as-of | Gold (or separate MARKET schema) | PT, WACC, trading setup |
| 6 | **Segment/revenue model mart** (product/geo cut of XBRL segments) | Gold | initiation T2 |
| 7 | **Peer set / comps as-of snapshot** | Gold or graph (COMPETES_WITH) | T3, sector |
| 8 | Keep **Subject Bundle** as ER agent entrypoint; add sections: `financials_history`, `latest_earnings_release`, `filings_index` | Serving contract | All product skills |

---

## 6. Practical integration pattern (today)

Without waiting for new tables, an ER agent stack can be:

```text
edgartools-platform
  ├── TICKER_REFERENCE / MDM company     → resolve identity
  ├── FINANCIAL_DERIVED + FINANCIAL_FACT → model actuals / initiation history
  ├── EARNINGS_RELEASE                   → post-print GAAP flash
  ├── FILING_* + bronze text             → research attachments
  ├── OWNERSHIP + 13F + graph bundle     → insider / holder narrative
  └── market/price_provider (optional)   → prices for WACC/PT if deps installed

external / firm
  ├── Consensus + guidance values
  ├── Transcripts / IR decks
  ├── Earnings calendar
  └── Excel model + thesis store
```

---

## 7. Bottom line

| Question | Answer |
|----------|--------|
| Can Gold/MDM/Neo4j run **full** ER skills alone? | **No** |
| Can they run a **strong SEC fundamentals + ownership + filing spine** for ER? | **Yes** |
| Highest leverage next data products? | **Consensus, guidance values, earnings calendar, transcripts, productized prices** |
| Best current agent API shape? | **Subject Bundle + financial_derived + earnings_release + filing_detail** |

---

*Cross-ref: ER I/O inventory `er-skills-io.md`; platform `docs/data-architecture.md`, `config/gold_schemas.yaml`, `docs/neo4j.md`, `docs/subject-bundle-read.md`.*
