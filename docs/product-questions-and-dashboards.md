# Product Questions & Dashboard Designs

What kinds of questions can the EdgarTools Platform answer today, and how should
dashboards surface them?

This document is a product brainstorm grounded in **existing gold tables and
MDM/graph surfaces** — not a commitment to build every view. Existing UIs
already cover a subset (summary KPIs, company lookup, filing volume, basic
ownership/funds, financial factors). Designs below mark **today vs next**.

Related: [project-overview.md](project-overview.md) ·
[data-architecture.md](data-architecture.md)

---

## Product decisions (locked / superseding)

| Decision | Choice | Implication |
| --- | --- | --- |
| **Primary consumer (v1)** | **Agent Decision Surface** (machine-readable) | Contracted gold/feature facts first; not dashboard-first |
| **Human role (v1)** | **Human Audit View** only | Streamlit shows the same rows the agent reads; not the source of truth |
| **Trading** | Inputs only — no execution | Platform does not place orders or manage portfolios |
| **Unit of agent read** | **Decision Graph Bundle** (multi-entity) | Not a single factor row; company-rooted graph-shaped payload |
| **v1 bundle contents** | **Trading-Relevant Neighborhood (C)** | Insiders/employment + holdings when present + auditor when present + subject accounting features; not full type registry / not ADV-first |
| **Edge currency** | **Current default + optional history (C)** | Default Current Neighborhood; history only on request with explicit not-current markers |
| **Factor freshness** | **As-Of Decision Features** | Features at watermark are latest complete calc; may use multi-period history as *inputs*; null ≠ zero when history insufficient |
| **Factor slice on bundle** | **FY + newer interim (B)** | Primary Annual Feature Vector always when available; Latest Interim Feature Vector only if period_end after last FY |
| **Agent delivery (v1)** | **Snowflake Decision Contract (A)** | Published Snowflake objects are the contract; audit UI reads the same; S3/API optional later |
| **Bundle identity** | **Decision Watermark (C)** | Silver parse/completeness + graph generation + gold feature as-of + business date; bronze sha only if persist used; mismatch → invalid |
| **Ingest doctrine** | **ADR 0002** | Silver SoE; edgartools-exclusive SEC I/O; bronze opt-in or non-edgartools only — see `docs/doctrine-data-plane.md` |
| **Hosting for audit UI** | Streamlit-in-Snowflake | Thin audit over the contract; `examples/dashboard` is prototype only |
| **Market data (v1)** | **Pure-SEC Decision Features (A)** | No prices/market cap/PE on the surface; agent joins market data elsewhere if needed |
| **Subject universe** | **Tracked / active only (B)** | Bundles for maintained universe, not every gold COMPANY row |
| **Partial data** | **Partial bundle + coverage flags (A)** | Never silent empty; empty ≠ unavailable; agent may abstain |
| **Human Audit View (v1)** | **Three dashboards (C)** | Company 360 + Screener + Insider Watch ship in v1 |
| **Dashboard data path** | **Dual mode (B)** | Agent View Mode = contract only; Explore Mode = free gold, labeled not-for-agent |
| **Contract versioning** | **Explicit Decision Contract Version (A)** | Version field on every bundle; agents pin; breaking changes bump |
| **13F / holdings currency** | **Latest Complete Holdings Period (A)** | Lagged source OK; expose period + lag in coverage; not same-day positions |
| **Multi-subject access** | **Screen + single bundle (A)** | Subject Feature Screen for rank/filter; Subject Bundle Read for deep-dive |
| **Auth (v1)** | **Deferred Access Control** | No product OAuth now; pluggable after go-live; session/Snowflake trust only |
| **Watermark mismatch** | **Fail closed — no Agent-Grade Read (A)** | Graph vs gold misalignment invalidates trading inputs |

P0 human dashboards (Company 360 / Screener / Insider Watch) are **candidates for audit views**, subordinate to the published decision contract.

---

## Who is asking?

Different users care about different question families:

| Persona | Goal | Typical question style |
| --- | --- | --- |
| **Research analyst** | Company / sector insight | “How healthy is AAPL’s balance sheet?” |
| **Insider / ownership researcher** | Who bought or sold | “Did directors sell after earnings?” |
| **Institutional-flow analyst** | 13F positioning | “Who increased holdings in NVDA last quarter?” |
| **Adviser / fund ops** | RIA and private funds | “Which advisers manage large private funds?” |
| **Forensic / risk** | Accounting red flags | “Which companies have rising Beneish M?” |
| **Platform operator** | Pipeline health | “Is gold fresh? Did bootstrap finish?” |
| **Compliance / entity ops** | MDM + graph truth | “Is this person linked to both companies?” |

Clarifying who you prioritize first changes which dashboards ship first.

---

## Questions the product can answer

Grouped by domain. Each item notes the **primary gold/MDM source**.

### A. Universe & company identity

| # | Question | Data source |
| --- | --- | --- |
| A1 | How many companies / tickers are in the tracked universe? | `COMPANY`, `TICKER_REFERENCE` |
| A2 | What is the CIK, SIC industry, state of incorporation, and fiscal year-end for ticker X? | `COMPANY`, `TICKER_REFERENCE` |
| A3 | Which industries (SIC) dominate the universe? | `COMPANY` |
| A4 | Where are companies incorporated (state / country maps)? | `COMPANY` |
| A5 | What entity type is this filer (operating company vs other)? | `COMPANY` |

### B. Filing activity & disclosure cadence

| # | Question | Data source |
| --- | --- | --- |
| B1 | How many filings landed this week / month / year? | `FILING_ACTIVITY` |
| B2 | Which form types are most common? | `FILING_ACTIVITY` |
| B3 | Who are the heaviest filers? | `FILING_ACTIVITY` + `COMPANY` |
| B4 | What did company X file recently (timeline + accession list)? | `FILING_ACTIVITY`, `FILING_DETAIL` |
| B5 | How has XBRL adoption changed over time? | `FILING_ACTIVITY.is_xbrl` |
| B6 | What new filings appeared on business date D (daily discovery)? | Daily index → silver/gold activity |

### C. Insider ownership (Forms 3 / 4 / 5)

| # | Question | Data source |
| --- | --- | --- |
| C1 | Who are the reporting owners for company X? | `OWNERSHIP_HOLDINGS` / activity + silver owners |
| C2 | What insider buys/sells happened in the last N days? | `OWNERSHIP_ACTIVITY` |
| C3 | Which companies have the most insider transaction volume? | `OWNERSHIP_ACTIVITY` |
| C4 | Did officers/directors acquire or dispose shares around an earnings date? | Ownership + `EARNINGS_RELEASES` |
| C5 | What is the transaction code mix (open market, grant, exercise…)? | `OWNERSHIP_ACTIVITY` |
| C6 | How large were the largest insider sells this quarter? | `OWNERSHIP_ACTIVITY` |

### D. Institutional holdings (13F)

| # | Question | Data source |
| --- | --- | --- |
| D1 | Which managers hold CUSIP / issuer Y? | `INSTITUTIONAL_HOLDINGS` |
| D2 | What did manager M report in the latest 13F period? | `INSTITUTIONAL_HOLDINGS` |
| D3 | Which holdings grew or shrank quarter-over-quarter? | Derived from successive 13F periods |
| D4 | Concentration: top positions by market value for a manager? | `INSTITUTIONAL_HOLDINGS` |

### E. Fundamentals, earnings & compensation

| # | Question | Data source |
| --- | --- | --- |
| E1 | What is revenue, assets, FCF, margins for company X by fiscal period? | `FINANCIAL_DERIVED`, `FINANCIAL_FACTORS` |
| E2 | What is 3y / 5y revenue or net-income CAGR? | `FINANCIAL_FACTORS` |
| E3 | How do liquidity / leverage ratios look (current, debt/assets, cash/assets)? | `FINANCIAL_FACTORS` |
| E4 | What GAAP revenue / EPS did the latest earnings release state? | `EARNINGS_RELEASES` |
| E5 | Who are the named executives and what is total compensation? | `EXECUTIVE_RECORDS` |
| E6 | Are there accounting red flags (Beneish M, Altman Z, Piotroski F, auditor change)? | `ACCOUNTING_FLAGS` |

### F. Investment advisers & private funds (ADV)

| # | Question | Data source |
| --- | --- | --- |
| F1 | Where are adviser offices located? | `ADVISER_OFFICES` |
| F2 | What disclosure events has adviser A reported? | `ADVISER_DISCLOSURES` |
| F3 | Which private funds does an adviser manage, and at what AUM? | `PRIVATE_FUNDS` |
| F4 | Who manages the largest private funds in the loaded set? | `PRIVATE_FUNDS` |

### G. Relationships & graph (MDM)

| # | Question | Data source |
| --- | --- | --- |
| G1 | Who are the insiders of company X in the master graph? | Graph edges `IS_INSIDER` |
| G2 | Which funds does adviser A manage? | `MANAGES_FUND` |
| G3 | Does person P appear across multiple issuers? | Person entity + edges |
| G4 | Who audits company X? | `AUDITED_BY` |
| G5 | Is graph parity healthy (MDM vs hosted graph)? | `mdm verify-graph` / operator status |

### H. Platform health (operators)

| # | Question | Data source |
| --- | --- | --- |
| H1 | When was gold last refreshed? Are dynamic tables lagging? | `EDGARTOOLS_GOLD_STATUS`, source status |
| H2 | Did the latest `load_history` / bootstrap succeed end-to-end? | Run manifests, Step Functions, status tables |
| H3 | How many companies are still `bootstrap_pending`? | MDM / `sec_company_sync_state` |
| H4 | Are silver shards complete for the current watermark? | Reconcile / integrity tooling |

---

## What already exists

| Surface | Covers roughly |
| --- | --- |
| `infra/snowflake/streamlit/streamlit_app.py` | Summary KPIs, company search, financial factors, filing mix, pipeline status hooks |
| `examples/dashboard/edgar_universe_dashboard.py` | Overview, maps, industry, filings, ownership/funds, company lookup |
| `examples/mdm_graph_dashboard/` | MDM / graph operator review |

**Gap vs opportunity:** existing UIs are strong on **coverage and volume** and
light on **investigative workflows** (insider around earnings, 13F QoQ change,
forensic screens, relationship browser).

---

## Dashboard designs (proposed)

Six focused dashboards. Each lists purpose, primary questions, layout, filters,
key charts/tables, and build priority.

### Dashboard 1 — Platform Command Center *(operator)*

**Purpose:** One screen that answers “is the warehouse healthy?”

**Answers:** H1–H4, A1, B1

**Layout**

```text
┌──────── KPIs ─────────────────────────────────────────────┐
│ Companies │ Filings │ Latest filing │ Gold lag │ MDM lag  │
├─────────────┬───────────────────────┬─────────────────────┤
│ Pipeline    │ Freshness by gold     │ Tracking status     │
│ run status  │ table                 │ pie (active/pending)│
├─────────────┴───────────────────────┴─────────────────────┤
│ Filing volume last 30 days (line)                         │
│ Recent failed / partial runs (table)                      │
└───────────────────────────────────────────────────────────┘
```

**Filters:** environment (dev/prod), last N days  
**Priority:** High for operators · **Status:** partially exists in summary + status queries  
**Data:** `EDGARTOOLS_GOLD_STATUS`, `COMPANY`, `FILING_ACTIVITY`, run manifests

---

### Dashboard 2 — Company 360 *(analyst default)*

**Purpose:** Everything useful about one company on one page.

**Answers:** A2, B4, C1–C2, E1–E6, D1 (as subject issuer), G1/G4 if graph live

**Layout**

```text
┌ Header: Name · Tickers · CIK · SIC · FYE ─────────────────┐
│ KPI strip: Rev (latest FY) · Current ratio · Debt/assets  │
│           · Insider txns 90d · Latest 10-K/10-Q date      │
├──────── Tabs ─────────────────────────────────────────────┤
│ Overview │ Filings │ Financials │ Insiders │ 13F holders  │
│ Earnings │ Execs & pay │ Flags │ Relationships            │
└───────────────────────────────────────────────────────────┘
```

**Tab sketches**

| Tab | Widgets |
| --- | --- |
| Overview | Industry, addresses summary, filing cadence sparkline |
| Filings | Form mix bar, recent filings table (date, form, accession) |
| Financials | Revenue/NI/FCF trend; ratio cards; CAGR chips |
| Insiders | Recent Form 4 table; buy vs sell volume chart |
| 13F holders | Top institutional holders of issuer (if CUSIP join available) |
| Earnings | Latest GAAP metrics from 8-K releases |
| Execs & pay | Compensation table by fiscal year |
| Flags | Beneish / Altman / Piotroski / auditor change |
| Relationships | Graph-backed insider/auditor/parent edges |

**Filters:** ticker/name search, fiscal period (FY vs Q), date range  
**Priority:** Highest product surface · **Status:** partial (lookup + factors + filings)  
**Data:** all major gold tables for one `company_key` / CIK

---

### Dashboard 3 — Insider Watch *(research / compliance)*

**Purpose:** Cross-company insider flow, not one issuer at a time.

**Answers:** C2–C6, C4 (with earnings join)

**Layout**

```text
┌ Filters: date range · form (3/4/5) · role · ticker · min $ ─┐
│ KPIs: # txns · # buyers · # sellers · net shares · $ notional│
├──────────────────────────┬──────────────────────────────────┤
│ Buy vs sell over time    │ Top issuers by sell notional     │
├──────────────────────────┴──────────────────────────────────┤
│ Cluster: large sells within ±5 days of earnings             │
│ Transaction tape (sortable table)                           │
└─────────────────────────────────────────────────────────────┘
```

**Key interactions**

- Click a transaction → open Company 360 + accession deep link  
- Toggle “officers/directors only”  
- Highlight open-market codes vs grants/exercises  

**Priority:** High differentiation · **Status:** thin today (top counts + recent list)  
**Data:** `OWNERSHIP_ACTIVITY`, `OWNERSHIP_HOLDINGS`, `EARNINGS_RELEASES`, `COMPANY`

---

### Dashboard 4 — Institutional Positioning *(13F)*

**Purpose:** Manager ↔ security positioning over time.

**Answers:** D1–D4

**Layout**

```text
Mode toggle: [ By manager ]  [ By issuer / CUSIP ]
┌ Filters: period · manager · CUSIP/issuer · min value ──────┐
│ Holdings bar (top N) │ Put/call / discretion mix           │
│ QoQ change waterfall or up/down lists                      │
│ Full holdings table with shares, value, voting authority   │
└────────────────────────────────────────────────────────────┘
```

**Priority:** Medium–high once 13F coverage is dense · **Status:** gold table exists; UI thin  
**Data:** `INSTITUTIONAL_HOLDINGS` (+ period-over-period view models if needed)

---

### Dashboard 5 — Fundamentals Screener *(research)*

**Purpose:** Rank and filter many companies by accounting factors (no market prices required).

**Answers:** E1–E3, E6 across the universe

**Layout**

```text
┌ Filters: SIC · FY only · min revenue · factor ranges ──────┐
│ Results table (sortable): ticker, rev, ROIC, CAGRs, ratios  │
│ Side panel: distribution histogram for selected factor      │
│ “Send to Company 360” action                                │
└────────────────────────────────────────────────────────────┘
```

**Example screens**

- High debt/assets + falling current ratio  
- Strong 3y revenue CAGR with improving FCF/revenue  
- Elevated accruals_to_assets / Beneish outliers  

**Priority:** High for research persona · **Status:** company-level factors only today  
**Data:** `FINANCIAL_FACTORS`, `FINANCIAL_DERIVED`, `ACCOUNTING_FLAGS`, `COMPANY`

---

### Dashboard 6 — Adviser & Fund Explorer *(ADV)*

**Purpose:** Navigate RIAs, offices, disclosures, private funds.

**Answers:** F1–F4, G2

**Layout**

```text
┌ Search adviser · CRD/file number · fund name ──────────────┐
│ Map or state breakdown of offices                          │
│ Fund list (AUM, type) │ Disclosure event timeline          │
│ Link to managed-fund graph edges when available            │
└────────────────────────────────────────────────────────────┘
```

**Priority:** Depends on ADV bronze completeness · **Status:** partial in ownership/funds example  
**Data:** `ADVISER_OFFICES`, `ADVISER_DISCLOSURES`, `PRIVATE_FUNDS`, MDM graph

---

### Optional Dashboard 7 — Relationship Browser *(MDM graph)*

**Purpose:** Visual “who is connected to whom?”

**Answers:** G1–G5

**Layout:** entity search → ego network (1–2 hops) → edge type filters →
property panel → parity badge (eligible vs current-at-watermark).

**Priority:** After graph generations are trusted in the target env  
**Status:** separate MDM graph dashboard exists as operator tooling

---

## Suggested product roadmap (dashboards)

Aligned to locked decisions: **analyst-first**, **Streamlit-in-Snowflake**, **accounting-only**.

| Phase | Ship | Why |
| --- | --- | --- |
| **P0** | **Company 360** (complete analyst tabs) | Default daily path: one ticker → filings, financials, insiders, earnings, flags |
| **P0** | **Fundamentals Screener** | Cross-company ranking on pure-SEC factors (CAGR, ratios, accruals) |
| **P0** | **Insider Watch** | Cross-issuer Form 3/4/5 tape; deep-link into Company 360 |
| **P0.5** | Thin **ops health strip** (gold lag, latest filing date) | Not a full Command Center — enough so analysts trust freshness |
| **P1** | Institutional Positioning (13F) | After period coverage is dense enough for QoQ |
| **P2** | Adviser & Fund Explorer + Relationship Browser | ADV bronze + trusted graph generations |
| **Later** | Full Platform Command Center | When operator persona becomes a first-class product goal |

### SiS implementation notes (v1)

- Extend `infra/snowflake/streamlit/streamlit_app.py` rather than inventing a new app host.
- Shared nav: **Company 360 · Screener · Insiders · (Health)**.
- All queries against `EDGARTOOLS_GOLD` (and status tables only for the health strip).
- No market-price joins; label factors as “accounting-only” in the UI.

---

## Sample user stories (for prioritization)

1. *As an analyst*, I search **AAPL**, see latest FY ratios, Form 4 tape, and
   earnings GAAP metrics without leaving one page.
2. *As a risk analyst*, I list companies with **rising accruals** and
   **auditor changes** in the last two fiscal years.
3. *As a markets researcher*, I filter Form 4 **open-market sells > $1M** in
   the last 14 days and jump to the issuer page.
4. *As an operator*, I confirm **gold lag < 24h** and **zero failed Stage 2 MDM
   runs** after last night’s load.
5. *As a fund researcher*, I open an adviser and list **private funds by AUM**
   plus disclosure events.

---

## Grill outcome (2026-07-17)

Grilling closed with **shared understanding**. Authoritative ADR:

[`docs/adr/0001-agent-decision-surface-first.md`](adr/0001-agent-decision-surface-first.md)

Glossary terms live under **Agent decision support** in root `CONTEXT.md`.

**Next skill:** `/to-spec` (then `/to-tickets` → `/implement` per ticket).

### Deferred (not v1 blockers)

- Pluggable OAuth / product access layer after go-live  
- Market price overlay contract  
- Neighborhood history full UX  
- Physical Snowflake object layout (views vs procedures) — implementation detail for spec  
- Exact column lists per Decision Feature — for `/to-spec`  

---

## How this maps back to `edgartools`

Users never need to call the library for these questions. The platform already:

1. Captured filings into bronze  
2. Used **edgartools** (and local parsers) to normalize ownership, 13F, earnings,
   proxy pay into silver  
3. Published gold tables those dashboards query  

The product value is **question-ready tables + UX**, not “wrap another SEC API
client.”
