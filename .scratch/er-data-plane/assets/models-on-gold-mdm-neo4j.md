# Research: Models buildable on edgartools Gold / MDM / Neo4j

**Date:** 2026-07-24  
**Scope:** What financial / analytical **models** can be constructed from **current** platform surfaces (plus optional External joins).  
**Not:** Implementation plan.  
**Related:** ERDP phase-1 specs (consensus, guidance, calendar, transcript) are **not yet in gold** — noted where they unlock more models.

---

## 1. Data inventory (model inputs available today)

### 1.1 Gold (`EDGARTOOLS_GOLD` / export)

| Surface | Model-relevant fields |
|---------|----------------------|
| **COMPANY / TICKER_REFERENCE** | CIK, name, SIC, FYE, ticker, exchange |
| **FINANCIAL_FACTS** | XBRL concept-level history (fine grain, segment string) |
| **FINANCIAL_DERIVED** | Revenue, GP, EBITDA, EBIT, NI, EPS diluted, BS items (cash, debt, AR, inv, WC components), OCF, capex, **FCF**, margins, ROIC/ROE/ROA, shares; dbt adds YoY, TTM, peer ranks |
| **FINANCIAL_FACTORS** | Accounting-only factors (growth CAGRs, profitability, WC, shares) — **no price/PE** by design |
| **EARNINGS_RELEASES** | GAAP rev/NI/EPS flash, FY/FQ, has_non_gaap, has_guidance |
| **FILING_*** | Form timeline, accession, report dates |
| **OWNERSHIP_*** | Form 3/4/5 txn shares, prices, codes, holdings snapshots |
| **INSTITUTIONAL_HOLDINGS** | 13F CUSIP, shares, MV, voting, manager CIK |
| **EXECUTIVE_RECORDS** | Pay components by NEO/year |
| **ACCOUNTING_FLAGS** | Auditor, Beneish M, Altman Z, Piotroski F, ICFR |
| **ADV / private funds** | Adviser offices, disclosures, fund AUM (manager world) |

### 1.2 MDM

| Entity / edge | Model use |
|---------------|-----------|
| **Company** | Universe, ticker↔CIK, parent link |
| **Person** | Insider / executive identity |
| **Security** | CUSIP/title for holdings models |
| **Adviser / Fund** | Manager/fund graphs, AUM |
| **Audit firm** | Auditor continuity |
| **Relationships** | IS_INSIDER, HOLDS, INSTITUTIONAL_HOLDS, EMPLOYED_BY, AUDITED_BY, HAS_PARENT_COMPANY, MANAGES_FUND, … |

### 1.3 Neo4j (Snowflake-hosted graph)

| Product | Model use |
|---------|-----------|
| **GRAPH_NODES / GRAPH_EDGES** | Neighborhood features, network scores, holder/insider concentration |
| **Subject Bundle** | Agent-grade package: insiders, employment+pay, 13F holders, auditor, parent, pure-SEC features |

### 1.4 Optional (not gold product)

| Module | Adds |
|--------|------|
| `market/price_provider` + `wacc.py` | Price, mcap, beta, rf, ERP → **WACC, EV, multiples** (External join) |

### 1.5 Planned (ERDP, not live)

Consensus, guidance **values**, earnings calendar, transcripts → unlock beat/miss models, guide-vs-actual, event models.

---

## 2. Model catalog by readiness

**Legend**

| Readiness | Meaning |
|-----------|---------|
| **A — Pure platform** | Gold/MDM/Neo4j only |
| **B — Platform + light External** | Needs price/mcap/beta (or free yfinance) |
| **C — Needs ERDP-01…04 or paid Street** | Consensus/calendar/transcript/guide values |
| **D — Structural gap** | Needs segment mart, product P&L, LBO debt schedules, etc. |

---

### A. Pure platform models (buildable now)

| Model | Inputs from platform | Outputs | Notes |
|-------|---------------------|---------|--------|
| **Historical 3-statement style summary** | FINANCIAL_DERIVED (+ FACTS for detail) | Multi-year IS/BS/CF-like views | Not full linked Excel; good “history pack” for initiation Task 2 seed |
| **Quality / factor screen** | FINANCIAL_FACTORS, DERIVED, SIC peer ranks | Scores, ranks, filters | Aligns with Subject Feature Screen |
| **Growth model (CAGR / YoY / TTM)** | DERIVED + dbt growth/TTM columns | Growth vectors | Already partially in gold |
| **Profitability model** | Margins, ROE/ROA/ROIC | Margin bridges, trend | Pure SEC |
| **Cash conversion / FCF model** | OCF, capex, FCF, WC items | FCF yield **needs price** for yield; FCF level pure SEC | Level A; yield → B |
| **Leverage & liquidity model** | Debt, cash, current assets/liab | Net debt (book), current ratio, leverage ratios | Book leverage; market leverage → B |
| **Earnings event flash model** | EARNINGS_RELEASES | QoQ/YoY GAAP flash deltas | No Street beat without consensus (C) |
| **Accounting forensic model** | ACCOUNTING_FLAGS | M-score, Z-score, F-score, auditor change flags | Screening / red flags |
| **Insider trading signal model** | OWNERSHIP activity/holdings + MDM IS_INSIDER | Buy/sell intensity, cluster buys, Form 4 sequences | Network via Neo4j |
| **Institutional ownership / 13F model** | INSTITUTIONAL_HOLDINGS + graph | Holder concentration, churn, smart-money flows | Manager CIK universe |
| **Parent–sub / structure model** | HAS_PARENT + subsidiary evidence | Org tree features | Bundle `has_parent` |
| **Executive pay / governance model** | EXECUTIVE_RECORDS + EMPLOYED_BY | Pay vs size (size from rev/assets), pay growth | Pay-for-performance needs TSR → B |
| **Filing intensity / disclosure model** | FILING_ACTIVITY | Event rates, 8-K cadence | Catalyst density without calendar (C improves) |
| **Peer accounting comparables (book)** | DERIVED + SIC peer ranks | Relative margins, growth, ROIC vs peers | Multiples need price → B |
| **Altman/Beneish-style risk model** | ACCOUNTING_FLAGS + DERIVED | Distress / earnings manipulation screens | |
| **Subject Bundle decision features** | Bundle + Feature Screen | As-of pure-SEC feature vector | Agent-grade path |
| **Graph neighborhood score** | Neo4j edges | Insider count, top holders, auditor, parent depth | GDS algorithms optional |

---

### B. Platform + market External (price / mcap / beta)

Uses gold fundamentals **plus** External price join (or `price_provider` / future Gold MARKET).

| Model | Platform inputs | External inputs | Outputs |
|-------|-----------------|-----------------|---------|
| **WACC (CAPM)** | Debt, interest, tax, pretax income, SIC | mcap, beta, rf, ERP | WACC — **code already in `wacc.py`** |
| **Enterprise value / equity bridge** | Cash, debt, shares | Price → mcap | EV, equity value |
| **Trading comps (multiples)** | Peers via SIC/MDM, EBITDA/rev/EPS | Price, mcap | EV/EBITDA, P/E, EV/Sales |
| **Simple DCF (historical FCF run-rate)** | FCF history, growth | WACC (B), terminal g assumption | Rough intrinsic value |
| **FCF yield / earnings yield** | FCF, NI, EPS | Price | Yields |
| **Net debt / EV** | Book net debt | EV | Leverage |
| **TSR / pay-for-performance** | EXECUTIVE_RECORDS | Price history | Relative TSR |
| **Event study (Form 4 / 8-K)** | Ownership, filings | Daily returns | Abnormal returns |
| **Short-horizon quant factors** | FINANCIAL_FACTORS | Returns | Cross-section |

**Without External market data, B-class models stop at “accounting inputs ready.”**

---

### C. Unlocked by ERDP-01…04 (planned) or Street data

| Model | Needs | Platform after ERDP |
|-------|-------|---------------------|
| **Beat/miss model** | Consensus + actuals | ERDP-01 + EARNINGS_RELEASES |
| **Estimate revision model** | Multi as_of consensus | ERDP-01 history |
| **Guide vs actual model** | Guidance values + actuals | ERDP-02 + EARNINGS_RELEASES |
| **Preview scenario framework** | Consensus + calendar + optional guide | ERDP-01+02+03 |
| **Catalyst timing model** | Forward calendar | ERDP-03 |
| **Post-print NLP / transcript model** | Transcript text | ERDP-04 + optional embeddings |
| **Whisper / options-implied** | Options | Still External (not ERDP) |

---

### D. Structural gaps (hard on current platform alone)

| Model | Missing inputs |
|-------|----------------|
| **Full sell-side integrated forecast model** | Forward assumptions, segment KPIs, driver tree (user Excel) |
| **Product/geo revenue model (20–30 rows)** | Curated segment mart (raw XBRL segment only today) |
| **LBO / debt schedule / returns** | Capital structure deal terms, sources & uses (not SEC gold) |
| **Merger A/D** | Deal terms, pro forma adjustments |
| **Bank / insurer / REIT specialized models** | Sector KPI extracts (NIM, combined ratio, FFO) not first-class |
| **Unit economics (SaaS ARR, NRR)** | Not standardized in gold (may exist sporadically in XBRL) |
| **Street rating / PT history** | External |

---

## 3. Mapping to financial-services skills / agents

| Skill / agent area | Models platform can feed |
|--------------------|---------------------------|
| **initiating-coverage Task 2** | Seed history from DERIVED/FACTS; peer ranks; not full Excel model |
| **initiating-coverage Task 3** | Book comps + DCF inputs (FCF); full DCF needs B (WACC/price) |
| **model-update** | Actuals plug from DERIVED/EARNINGS_RELEASES; guide/consensus when ERDP-01/02 live |
| **earnings-analysis** | Flash GAAP, forensics, ownership; transcript when ERDP-04 |
| **earnings-preview** | Weak until ERDP-01+03 |
| **idea-generation / screens** | Strong: factors, forensics, 13F, insider graph |
| **sector-overview** | Multi-issuer DERIVED + SIC peers |
| **model-builder agent** | History + optional WACC helper; full templates still skill-driven |

---

## 4. Recommended model “products” to build on platform (priority)

### Tier 1 — pure SEC, high leverage, no new vendors

1. **Issuer fundamentals pack** (history + factors + ranks)  
2. **Forensic / quality scorecard** (M/Z/F + leverage + auditor)  
3. **Insider signal pack** (Form 4 + graph neighborhood)  
4. **13F holder / flow pack** (concentration, top holders, QoQ change)  
5. **Earnings flash pack** (8-K GAAP + filing context)

### Tier 2 — add External market join

6. **WACC + EV pack** (reuse `wacc.py`)  
7. **Trading comps pack** (SIC peers + multiples)  
8. **Simple DCF scaffold** (historical FCF → project with user growth / WACC)

### Tier 3 — after ERDP phase-1

9. **Beat/miss + revision pack** (consensus)  
10. **Guide-vs-actual pack**  
11. **Catalyst calendar model**  
12. **Transcript-linked earnings narrative pack**

---

## 5. Architecture patterns for models on this stack

```text
                    ┌─────────────┐
                    │ MDM / Graph │  identity + neighborhood
                    └──────┬──────┘
                           │
┌──────────────┐    ┌──────▼──────┐    ┌────────────────┐
│ Gold factors │───►│ Feature join│◄───│ External market│ (optional)
│ derived/facts│    │  (CIK,as_of)│    │ price/beta     │
└──────────────┘    └──────┬──────┘    └────────────────┘
                           │
                    ┌──────▼──────┐
                    │ Model layer │  SQL / Python / Excel export
                    │ screens,    │
                    │ DCF, comps, │
                    │ signals     │
                    └─────────────┘
```

| Pattern | When |
|---------|------|
| **SQL feature mart in Snowflake** | Screens, ranks, peer comps book metrics |
| **Subject Bundle consumption** | Agent-grade pure-SEC decisions |
| **Python model service** | WACC, DCF, event study (uses gold + price_provider) |
| **Excel export** | ER initiation / model-builder handoff |

---

## 6. Constraints that shape “what can be built”

1. **Pure-SEC gold factors exclude price** → valuation multiples and WACC need an explicit External join (by design).  
2. **No Street consensus in gold today** → beat/miss incomplete until ERDP-01.  
3. **Guidance is boolean only** → guide models wait for ERDP-02.  
4. **Segment string ≠ product model** → detailed revenue models need more structure.  
5. **Graph is relationship-rich** → excellent for ownership/governance models, not for P&L forecasts.  
6. **Agent-Grade vs Explore** → market-joined models are Explore/research unless a new contract section is defined.

---

## 7. Bottom line

| Question | Answer |
|----------|--------|
| Can you build serious models on gold/MDM/neo4j **today**? | **Yes** — historical fundamentals, factors, forensics, insider, 13F, structure, pure-SEC screens |
| Can you build full **equity valuation**? | **Partially** — accounting FCF/debt ready; **WACC/EV/multiples need market join** |
| Can you build **ER print workflow models**? | **Partially** — flash actuals yes; consensus/guide/calendar/transcript after ERDP-01…04 |
| Best near-term model products? | Fundamentals pack, forensic scorecard, insider + 13F packs, then WACC/comps with External price |

---

*Research only; no implementation. Cross-ref: data-architecture.md, gold_schemas, financial_derived/factors dbt, wacc.py, ERDP specs.*
