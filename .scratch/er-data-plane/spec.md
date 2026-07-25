# ER data plane — specification (draft)

**Status:** **planning freeze** — wayfinder destination reached; implementation tracks REQUIREMENTS.md.  
**Repo:** edgartools-platform  
**Consumers:** financial-services equity-research skills / agents  
**Evidence:** [assets/er-skills-io.md](./assets/er-skills-io.md), [assets/er-edgartools-gap-analysis.md](./assets/er-edgartools-gap-analysis.md)  
**Completeness:** [coverage-matrix.md](./coverage-matrix.md)

## 1. Purpose

Define what edgartools-platform must **expose** so equity-research workflows can run on a governed SEC + optional external join plane — without owning sell-side process state (thesis, Excel paths).

## 2. Completeness rule

Requirements cover ER skill scope when:

1. All **9** ER skills appear in the coverage matrix.  
2. Every required input class for each skill is classified: **Covered | Partial | External | Gap | N/A**.  
3. Every **Gap** maps to a requirement ID below (or is Out of scope on the map).  
4. Every **Covered** cell has product name + read path + acceptance criterion.

Phase-1 may leave many cells **External** or **Out of scope**; blanks are not allowed.

## 3. Phase-1 products (**locked** — ticket 01)

| ID | Product | Intent | Layer (**locked ticket 02**) |
|----|---------|--------|------------------------------|
| ERDP-01 | Consensus estimates | metric × period × value × as_of × source | **Gold Explore** — **detail:** [specs/ERDP-01-consensus-estimates.md](./specs/ERDP-01-consensus-estimates.md) |
| ERDP-02 | Guidance facts | metric × period × low/mid/high × as_of × accession | **Gold Explore** — **detail:** [specs/ERDP-02-guidance-facts.md](./specs/ERDP-02-guidance-facts.md) |
| ERDP-03 | Earnings calendar | expected date, time, pre/post, confirmed vs estimated | **Gold Explore** — **detail:** [specs/ERDP-03-earnings-calendar.md](./specs/ERDP-03-earnings-calendar.md) |
| ERDP-04 | Transcript MVP | event/accession pointer + optional text store | **Object store** + **Gold pointer** — **detail:** [specs/ERDP-04-transcript-mvp.md](./specs/ERDP-04-transcript-mvp.md) |
| ERDP-05 | Existing-surface ER read map | Document existing + new Gold read paths | Docs / serving contract |
| ERDP-06 | Pure-SEC vs market boundary | What stays in Decision Features vs external join (ADR 0001) | **Locked ticket 03** — see §3.1 |
| **ERDP-07** | **Market EOD join** | yfinance close/mcap/beta + gold fundamentals for WACC/EV/comps/PT | **Explore join** (not pure-SEC features) — **detail:** [specs/ERDP-07-market-eod-join.md](./specs/ERDP-07-market-eod-join.md); skill impact: [assets/er-skills-unblocked-with-eod.md](./assets/er-skills-unblocked-with-eod.md) |

**Deferred (not phase-1):** Snowflake **Gold MARKET table**; Street ratings/PT **history**; packaged peer-comps gold product (ad hoc comps via gold+EOD are in scope as recipes); macro calendar; segment revenue mart; IR decks as gold products; thesis/Excel workflow.

### 3.1 ERDP-06 — Pure-SEC vs market (locked — ticket 03)

| Rule | Decision |
|------|----------|
| ADR 0001 | **Unchanged** — pure-SEC Decision Features only |
| Phase-1 market data | **External only** (firm/vendor join; not Gold Decision Contract) |
| Phase-2 option | Separate Gold **Explore** MARKET surface allowed later; never in `subject_features` / Agent View without new ADR |
| Join key | ticker or CIK + `as_of` date |
| Agent-Grade | Must not include price/mcap/PE/EV in feature vectors or claim grade on smuggled market fields |

## 4. Non-goals

- Replacing financial-services skill markdown  
- Order execution or trading recommendations  
- Dashboard-first product (agent/contract first per ADR 0001)

## 5. ERDP-05 — Existing-surface ER read map (draft)

**Status:** draft complete (ticket 05); promote Partial → Covered in the matrix only after acceptance criteria are attached per product.

Full map: [assets/erdp-05-existing-surface-read-map.md](./assets/erdp-05-existing-surface-read-map.md)

### Summary

| Surface (prefer Gold) | Grain | ER use | Limitation |
|----------------------|-------|--------|------------|
| `EDGARTOOLS_GOLD.TICKER_REFERENCE` / `COMPANY` | CIK / ticker | Identity, universe | No single ER identity contract |
| `FINANCIAL_FACTS` / `FINANCIAL_DERIVED` / `FINANCIAL_FACTORS` | CIK × period (× concept) | Model history, screens | Segment raw only; no product/geo mart |
| `EARNINGS_RELEASES` | CIK × 8-K event | Post-print GAAP flash | No consensus; guidance/non-GAAP values missing |
| `FILING_ACTIVITY` / `FILING_DETAIL` | accession | Filing index | Text/transcript not gold products |
| `OWNERSHIP_*` / `INSTITUTIONAL_HOLDINGS` | txn / holding | Insider / 13F | Bundle adds lag/period rules |
| Subject Bundle + Feature Screen | CIK @ Decision Watermark | Agent-grade neighborhood | Pure-SEC features only (no price/PE) |
| MDM `MDM_*` | entity / relationship | Resolve, track, graph SoE | Not a financials store |
| `GRAPH_NODES` / `GRAPH_EDGES` | node / edge | Neighborhood analytics | Snowflake-hosted; parity-gated |

**Agent-grade rule:** use Decision Watermark (`business_date`, `gold_run_id`, `graph_generation_id`, completeness/parity); abstain when `agent_grade` is false.

**Explore rule:** Gold free tables OK for research; do not claim Agent-Grade without watermark.

## 6. Phase-1 schemas + acceptance (**locked** — ticket 06)

Full sketches: [assets/erdp-01-04-schema-sketches.md](./assets/erdp-01-04-schema-sketches.md)

### 6.1 Tables (Gold Explore)

| ID | Gold table (export / dbt name) | Natural key (summary) |
|----|--------------------------------|------------------------|
| ERDP-01 | `CONSENSUS_ESTIMATES` | cik, metric, period_type, FY/FQ, statistic, as_of, source_system |
| ERDP-02 | `GUIDANCE_FACTS` | cik, metric, FY/FQ, as_of, accession, is_non_gaap |
| ERDP-03 | `EARNINGS_CALENDAR` | cik, FY, FQ, source_system (current via latest as_of) |
| ERDP-04 | Object store + `TRANSCRIPT_EVENTS` | cik, event_id, source_system; `storage_uri` required |

### 6.2 Acceptance IDs (summary)

| Series | Intent |
|--------|--------|
| A01.1–A01.5 | Consensus: history by as_of, identity join, beat/miss path, Explore labeling |
| A02.1–A02.4 | Guidance: numeric values, accession join, model-update path, Explore labeling |
| A03.1–A03.4 | Calendar: coverage %, session, catalyst-calendar path, Explore labeling |
| A04.1–A04.4 | Transcript: pointer + fetchable text, earnings-analysis path, not pure-SEC features |
| A05.1–A05.3 | Existing-surface doc completeness (Partial→Covered hardening) |
| A06.1–A06.3 | No market fields in ERDP-01…04; Agent-Grade pure-SEC; External market join |

### 6.3 Source policy (provider-agnostic schema; pilot sources locked)

| Product | Pilot primary | Fallback | Production later |
|---------|---------------|----------|------------------|
| Consensus (01) | `yahoo` | `firm_manual` (opt. `fmp`) | Street feed optional |
| Guidance (02) | `sec_8k` / `sec_10q` / `sec_10k` | `firm_manual` | — |
| Calendar (03) | `finnhub` | `yahoo` / `firm_manual` | Paid calendar optional |
| Transcript (04) | `ir_website` + `firm_manual` | — (pilot CIK list) | Paid transcript API optional |
| EOD (07) | `yahoo` / yfinance | — | Paid EOD optional |

Schema remains multi-source via `source_system`. Detail: `assets/free-sources-consensus-calendar-transcript.md` and each `specs/ERDP-0*.md`.

## 7. Acceptance (planning done)

- [x] Coverage matrix: 9 skills, 0 blanks (ticket 04)  
- [x] Phase-1 product list locked ERDP-01…06 (ticket 01)  
- [x] ERDP-06 pure-SEC vs market boundary locked (ticket 03)  
- [x] Layer placement for ERDP-01…04 locked (ticket 02)  
- [x] Schema sketches + acceptance criteria locked (ticket 06)  
- [x] Out-of-scope and External owners listed (map + tickets 01/03)  
- [x] `.planning/workstreams/er-data-plane/REQUIREMENTS.md` generated (ticket 07)  
- [x] ERDP-05 existing-surface draft written (ticket 05)  

## 8. Traceability

| Source | Path |
|--------|------|
| ER skill I/O | assets/er-skills-io.md |
| Gap analysis | assets/er-edgartools-gap-analysis.md |
| ERDP-05 read map | assets/erdp-05-existing-surface-read-map.md |
| Schema sketches | assets/erdp-01-04-schema-sketches.md |
| Coverage matrix | coverage-matrix.md |
| Wayfinder map | map.md |
| Milestone REQUIREMENTS | ../../.planning/workstreams/er-data-plane/REQUIREMENTS.md |
