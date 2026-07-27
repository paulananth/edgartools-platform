# ER skill × data-class coverage matrix

**Status:** frozen (ticket 04)  
**Rule:** No blank cells. Every cell is one of **Covered | Partial | External | Gap | N/A**.

| Label | Meaning |
|-------|---------|
| **Covered** | Named product + documented ER read path + acceptance criterion (ERDP-05+) |
| **Partial** | Platform product exists with useful fields, but ER-complete contract missing and/or fields incomplete |
| **External** | Firm/vendor data outside this repo (named owner); not a platform Gap |
| **Gap** | Needed for ER on-platform; maps to ERDP-* or Out of scope |
| **N/A** | Not a platform concern for that skill |

**Phase-1 product IDs:** ERDP-01 consensus · ERDP-02 guidance values · ERDP-03 earnings calendar · ERDP-04 transcript MVP · ERDP-05 existing-surface ER read map · ERDP-06 pure-SEC vs market boundary · **ERDP-07 market EOD join (yfinance Explore)**.

Sources: [assets/er-skills-io.md](./assets/er-skills-io.md), [assets/er-edgartools-gap-analysis.md](./assets/er-edgartools-gap-analysis.md), `docs/data-architecture.md`, `docs/subject-bundle-read.md`, `docs/neo4j.md`, `edgar_warehouse/config/gold_schemas.yaml`.

---

## Matrix

| Data class | catalyst-calendar | earnings-preview | morning-note | model-update | earnings-analysis | initiating-coverage | thesis-tracker | idea-generation | sector-overview |
|------------|:-----------------:|:----------------:|:------------:|:------------:|:-----------------:|:-------------------:|:--------------:|:---------------:|:---------------:|
| Identity (ticker/CIK) | Partial | Partial | Partial | Partial | Partial | Partial | Partial | Partial | Partial |
| Filings metadata | Partial | Partial | Partial | Partial | Partial | Partial | Partial | Partial | Partial |
| Filing / research text | Partial | Partial | Partial | N/A | Partial | Partial | N/A | N/A | Partial |
| Transcript | N/A | Partial | N/A | N/A | Partial | Partial | N/A | N/A | N/A |
| IR deck / supplemental | N/A | Gap | N/A | N/A | Gap | Gap | N/A | N/A | N/A |
| Historical financials (derived/facts) | N/A | Partial | Partial | Partial | Partial | Partial | Partial | Partial | Partial |
| Earnings 8-K GAAP snapshot | Partial | Partial | Partial | Partial | Partial | Partial | Partial | N/A | N/A |
| Non-GAAP values | N/A | Gap | Gap | Gap | Gap | Gap | N/A | N/A | N/A |
| Guidance **values** | N/A | Partial | Partial | Partial | Partial | Partial | N/A | N/A | N/A |
| Consensus + as-of | Partial | Partial | Partial | Partial | Partial | Partial | N/A | N/A | N/A |
| Earnings calendar date/time | Partial | Partial | Partial | N/A | N/A | N/A | Partial | N/A | N/A |
| Market price / mcap / beta | N/A | Partial | Partial | Partial | Partial | Partial | Partial | Partial | Partial |
| Options / implied move | N/A | External | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| Ownership / Form 4 | N/A | N/A | Partial | N/A | Partial | Partial | Partial | Partial | N/A |
| 13F / holders | N/A | N/A | N/A | N/A | Partial | Partial | Partial | Partial | N/A |
| Graph neighborhood (insider/audit/parent) | N/A | N/A | N/A | N/A | Partial | Partial | Partial | Partial | N/A |
| Segment / product-geo revenue | N/A | Partial | N/A | Partial | Partial | Gap | N/A | N/A | Partial |
| Peer comps pack | N/A | N/A | N/A | Partial | Partial | Partial | N/A | Partial | Partial |
| Street ratings / PT | N/A | N/A | External | Partial | Partial | Partial | Partial | N/A | N/A |
| Macro calendar | External | N/A | External | External | N/A | N/A | N/A | N/A | N/A |
| Excel model path | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| Thesis / conviction store | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| Executive / management & pay | N/A | N/A | Partial | N/A | Partial | Partial | Partial | N/A | N/A |
| Accounting forensic scores | N/A | N/A | N/A | N/A | Partial | Partial | Partial | Partial | N/A |
| Pure-SEC subject features | N/A | N/A | N/A | N/A | N/A | N/A | N/A | Partial | Partial |
| Competitive set / TAM / industry | N/A | N/A | N/A | N/A | N/A | External | N/A | External | External |
| Non-SEC news / wire | External | N/A | External | N/A | N/A | External | N/A | External | External |

---

## Footnotes — Covered / Partial → concrete product

Every **Partial** cell below maps to an existing platform surface. None are **Covered** yet: ER-facing read path + acceptance criteria land with **ERDP-05** (and serving-section additions noted in the gap analysis). Until then, agents use warehouse gold / Snowflake `EDGARTOOLS_GOLD` / MDM / Subject Bundle directly.

| # | Data class | Concrete product(s) | Layer | Notes (why Partial, not Covered) |
|---|------------|---------------------|-------|----------------------------------|
| F1 | Identity (ticker/CIK) | `TICKER_REFERENCE`; gold `COMPANY` / `dim_company`; silver `sec_company`, `sec_company_ticker`; MDM `mdm_company` (CIK, canonical name, ticker/exchange, tracking) | Gold + MDM | Resolve ticker→CIK and coverage universe; no single ER “identity” contract/doc yet (ERDP-05). |
| F2 | Filings metadata | Gold `FILING_ACTIVITY`, `FILING_DETAIL`, `dim_filing`; silver `sec_company_filing`, daily index `stg_daily_index_filing` | Gold / silver | Form, accession, filing/report dates, XBRL flags, primary doc; ER index section not yet on Subject Bundle. |
| F3 | Filing / research text | Bronze filing primary/attachments; silver/text `sec_filing_text` (normalized text path); not a gold narrative table | Bronze + silver | Text projection is **manual/backfill-only** (`targeted-resync --include-text`); not automated agent product. |
| F4 | Historical financials | Gold/export `SEC_FINANCIAL_DERIVED` / `financial_derived` (rev, GP, EBITDA, EBIT, NI, EPS, BS/CF, FCF, margins, ROIC/ROE/ROA, shares); `SEC_FINANCIAL_FACT` / `financial_facts` (XBRL concept, unit, period, **segment**); Subject Bundle `subject_features` (as-of pure-SEC vector, not full history) | Gold + Bundle features | Multi-year history is gold tables; Bundle only exposes feature vector, not full history section yet. |
| F5 | Earnings 8-K GAAP snapshot | Gold `EARNINGS_RELEASE` / `fact_earnings_release`: `revenue_gaap`, `net_income_gaap`, `eps_gaap_diluted`, FY/FQ, period_end, filing_date; flags `has_non_gaap`, `has_guidance` only | Gold | GAAP flash only; non-GAAP **values** and guidance **values** are Gaps (ERDP-02 family). |
| F6 | Ownership / Form 4 | Gold `OWNERSHIP_ACTIVITY`, `OWNERSHIP_HOLDINGS`; silver `sec_ownership_*`; MDM `IS_INSIDER`; Subject Bundle section `insiders` | Gold + MDM + Bundle | Txn-level Form 3/4/5 + graph edge; ER skill “insider narrative” contract = ERDP-05. |
| F7 | 13F / holders | Gold `SEC_THIRTEENF_HOLDING`; MDM `INSTITUTIONAL_HOLDS`; Subject Bundle `holders_of_subject`, `subject_as_manager_portfolio` | Gold + MDM + Bundle | Holdings period + lag rules exist on Bundle; no ER “holder pack” acceptance yet. |
| F8 | Graph neighborhood | Snowflake `GRAPH_NODES` / `GRAPH_EDGES`; MDM relationship instances (`IS_INSIDER`, `EMPLOYED_BY`, `AUDITED_BY`, `HAS_PARENT_COMPANY`, `INSTITUTIONAL_HOLDS`, …); Subject Bundle sections `insiders`, `employment`, `auditor`, `has_parent` | MDM + Neo4j (Snowflake-hosted) + Bundle | Deep-dive neighborhood for one CIK; not multi-issuer industry graph. |
| F9 | Segment / product-geo revenue | `SEC_FINANCIAL_FACT.segment` (raw XBRL segment string on facts) | Gold facts | **No** curated product/geo revenue model mart; initiation T2 still **Gap** for 20–30-row model. |
| F10 | Executive / management & pay | Gold `EXECUTIVE_RECORD` (name, role, salary/bonus/stock/option/total); MDM person + `EMPLOYED_BY`; Bundle `employment` (+ proxy pay) | Gold + MDM + Bundle | Names/pay/roles only — not full bios or org chart. |
| F11 | Accounting forensic scores | Gold `ACCOUNTING_FLAG` (auditor, PCAOB, Beneish/Altman/Piotroski-type scores); Bundle auditor section | Gold + Bundle | Useful for idea screens / risk notes; not a full forensic product. |
| F12 | Pure-SEC subject features | Subject Feature Screen + Bundle `subject_features` (FY + interim pure-SEC vectors; **no** price/PE/mcap per ADR 0001) | Serving contract | Idea/sector multi-issuer screens; ERDP-06 keeps market joins out of this vector. |
| F13 | Market price / mcap / beta | **ERDP-07**: `PriceProvider` / yfinance (close, mcap, beta); join ticker\|CIK + as_of; WACC via `wacc.py` | External Explore (not gold table) | Partial until A07.* + docs (ERDP-07). **Never** in pure-SEC features. |
| F14 | Peer comps (ad hoc) | Gold peer financials (SIC/ranks) + ERDP-07 prices → EV/EBITDA, P/E recipes | Gold + ERDP-07 | Not a packaged gold comps product; recipe-level Partial. |
| F15 | Model-derived PT | Gold FCF/EPS + ERDP-07 WACC/multiples → DCF/P/E PT | Gold + ERDP-07 | **Street** ratings/PT history remain External. |
| F16 | Consensus + as-of | Gold Explore `CONSENSUS_ESTIMATES` (`edgar_warehouse/explore/consensus_estimates.py`); `yahoo`/`firm_manual` pilot sources | Gold Explore (not Agent-Grade) | Reclassified Gap→Partial 2026-07-27 (ERDP-01 landed). No promoted data in prod as of this reclassification — 0% of the 50% universe-coverage bar in the ERDP-05-04 promotion checklist (`.scratch/erdp-coverage-promotion/issues/03-*.md`); `idea-generation`/`sector-overview` correctly N/A (no textual basis found). |
| F17 | Guidance **values** | Gold Explore `GUIDANCE_FACTS` (SEC 8-K extractor + `firm_manual`); `edgar_warehouse/explore/guidance_facts.py` | Gold Explore | Reclassified Gap→Partial 2026-07-27 (ERDP-02 landed). SEC-8-K path yielded 0 rows on the one real production run (Apple) — open whether 8-K is the right primary source (promotion checklist for this product still open, ticket 04 of `erdp-coverage-promotion`). |
| F18 | Earnings calendar date/time | Gold Explore `EARNINGS_CALENDAR`; `finnhub`/`yahoo`/`firm_manual` sources; `edgar_warehouse/explore/earnings_calendar.py` | Gold Explore | Reclassified Gap→Partial 2026-07-27 (ERDP-03 landed). `finnhub` path needs an uncleared commercial license — ops gate, not a code gap. `initiating-coverage`/`model-update`/`idea-generation`/`sector-overview` correctly N/A (no textual basis found). |
| F19 | Transcript | Gold Explore `TRANSCRIPT_EVENTS` (`ir_website` pointer + `firm_manual` copy); `edgar_warehouse/explore/transcript_events.py` | Gold Explore (not Agent-Grade) | Reclassified 2026-07-27 (ERDP-04 landed): `earnings-preview`/`earnings-analysis` Gap→Partial; `initiating-coverage` N/A→Partial (real need found, matrix previously missed it — `references/task1-company-research.md:27`); `morning-note` Gap→N/A (its only mention is scheduling, already covered by the Earnings-calendar row, not this one). `PILOT_CIKS={320193}` (Apple-only) + latest-quarter-only means history depth, not just CIK breadth, blocks `earnings-preview` (needs *prior* quarter) and `initiating-coverage` (needs 2-3 quarters) — see ticket 06 of `erdp-coverage-promotion`. |

**Covered cells:** none until ERDP-05/07 acceptance + docs, or (for F16–F19) the ERDP-05-04 promotion checklist passes per product. Promote Partial → Covered when read path + A0x pass.

### Skill unblock note (EOD scope expand)

With F13 only (no ERDP-01…04): **model-update valuation**, **initiating Task 3**, **idea/sector multiples**, **thesis PT vs spot** become practical. Full **earnings-preview / earnings-analysis / morning-note** still need consensus/calendar/transcript (Gaps). See `assets/er-skills-unblocked-with-eod.md`.

---

## Gap → ERDP / disposition

**Note (2026-07-27):** the four rows below are historical — they describe the original Gap→ERDP assignment made when these were still Gap cells. All four have since landed as real products and the matrix rows are now Partial (see F16–F19 above), not Gap. Kept here for the original disposition trail, not as current status.

| Data class | Disposition |
|------------|-------------|
| Consensus + as-of | **ERDP-01** — landed, see F16 |
| Guidance **values** | **ERDP-02** (enrich beyond `has_guidance`) — landed, see F17 |
| Earnings calendar date/time | **ERDP-03** — landed, see F18 |
| Transcript | **ERDP-04** — landed, see F19 |
| Non-GAAP **values** (as separate actuals product) | **Out of scope** phase-1 (REQUIREMENTS polish B): only `is_non_gaap` + numeric values on `GUIDANCE_FACTS`; full non-GAAP actuals product is Future |
| IR deck / supplemental | **Out of scope** phase-1 (object/pointer possible later; not ERDP-01…04) |
| Peer comps pack | **Out of scope** phase-1 (deferred on map) |
| Segment curated mart | **Out of scope** phase-1 (raw segment = Partial F9; full mart deferred) |
| Market price / mcap / beta | **Partial → ERDP-07** (yfinance Explore join); Snowflake Gold MARKET table still phase-2 / OOS as table product |
| Options / implied move | **External** (options vendor) |
| Street ratings / PT | **External** (sell-side / terminal) |
| Macro calendar | **External** / Out of scope platform (firm or macro vendor) |
| Competitive set / TAM | **External** (industry research; not SEC graph) |
| Non-SEC news / wire | **External** (news vendor) |
| Excel model path | **N/A** — user workspace |
| Thesis / conviction store | **N/A** — firm workflow system |

---

## New data classes discovered (vs seed)

Added at freeze (from gap analysis + skill I/O, not in original seed rows):

| Data class | Why |
|------------|-----|
| Executive / management & pay | Initiation T1, morning/earnings context; product = `EXECUTIVE_RECORD` + Bundle `employment` |
| Accounting forensic scores | Idea screens / risk; product = `ACCOUNTING_FLAG` |
| Pure-SEC subject features | Idea-generation / sector multi-issuer screens; Bundle + Feature Screen |
| Competitive set / TAM / industry | Initiation / sector / ideas — **External**, not platform SEC |
| Non-SEC news / wire | Morning-note / catalyst / ideas — **External** |

Also noted in gap analysis but **not** promoted to matrix rows (folded or out of scope):

| Candidate | Fold / disposition |
|-----------|-------------------|
| Coverage universe list | Folded into **Identity** (MDM tracking + ticker ref) |
| Prior-quarter guidance history | Subset of **Guidance values** (ERDP-02) |
| Whisper number | Folded into **Options / implied move** (External) |
| R&D / headcount builds | Occasional raw XBRL via **Historical financials** facts; no separate product |
| Bull/base/bear scenario store | Skill-local compute — **N/A** platform |
| WACC rf / ERP | Folded into **Market price / mcap / beta** External helpers (`wacc.py`) |
| ADV / adviser AUM | Secondary to pure equity ER — not a matrix row |
| Internal firm rating / PT | **N/A** with thesis store |

---

## Classification notes (seed → freeze deltas)

- **Identity / filings / financials / ownership / 13F / graph:** remain **Partial** (products named in footnotes F1–F8, F10–F12); not **Covered** until ERDP-05.
- **Transcript × initiating-coverage:** seed **Partial** → **N/A** (skill I/O does not require transcript; Task 1 is filings-led).
- **Earnings calendar × thesis-tracker:** seed **Partial** → **Gap** (upcoming catalysts need scheduled print time; filing date ≠ calendar product → ERDP-03).
- **Market price / options / Street ratings / macro:** seed **Gap** → **External** where phase-1 map defers productization (not platform Gaps).
- **Ownership × catalyst-calendar:** seed **Partial** → **N/A** (Form 4 is not a primary calendar catalyst input).
- **Filing text × catalyst / preview / sector:** **Partial** (bronze/daily filings support event discovery; text backfill incomplete).

---

## Gate

| Check | Status |
|-------|--------|
| 9/9 skills present as columns | **yes** |
| 0 blank cells | **yes** |
| Every Covered/Partial has product pointer | **yes** (footnotes F1–F12; 0 Covered) |
| Every Gap → ERDP-* or Out of scope | **yes** (see Gap table) |
| External owners named | **yes** (firm/vendor / optional market module; macro/news/sell-side/options) |
| New data classes listed | **yes** |

---

*Frozen by wayfinder ticket 04. Downstream: ERDP-05 read map (ticket 05), schemas (ticket 06), REQUIREMENTS generation (ticket 07).*
