# Spec: ER skill dashboards (phase-1 design)

**Status:** locked (wayfinder destination)  
**Date:** 2026-07-25  
**Repo:** edgartools-platform  
**Host:** Streamlit-in-Snowflake (`infra/snowflake/streamlit/streamlit_app.py`)  
**Related:** [map.md](./map.md) · [er-data-plane](../er-data-plane/) · [product-questions-and-dashboards.md](../../docs/product-questions-and-dashboards.md) · ADR 0001

---

## 1. Purpose

Design human dashboards that make **equity research (ER) skill workflows** operable against platform data — so an associate or agent can prepare previews, track catalysts, update models, and screen ideas without inventing numbers from training data.

Dashboards are **Human Audit / Explore research surfaces**, not a second Decision Contract. Agents still pin Subject Bundle / Feature Screen; humans use the same warehouse rows with richer joins and ERDP Explore products.

---

## 2. Personas & jobs-to-be-done

| Persona | JTBD | Primary dashboard |
|---------|------|-------------------|
| Sell-side / buy-side **ER associate** | Prep and publish product around earnings | **Earnings Desk** |
| Coverage **analyst** | Know what hits this week; morning meeting | **Catalyst Board** |
| Associate building **initiation / model** | One-issuer fundamentals + valuation Explore | **Research Workspace** |
| Idea / sector **scanner** | Find candidates; compare peers | **Idea & Sector Screen** |
| Platform **auditor** | Confirm what an agent would see | Agent View strip on every screen |

---

## 3. Product principles

1. **Skill-shaped, not table-shaped** — pages follow desk cadence (preview → print → note), not one widget per gold table.
2. **Mode honesty** — sticky Agent View / Explore chrome; Explore always shows the not-for-agent banner; ERDP-03/07 (and future 01/02/04) only in Explore.
3. **Graceful stubs** — if consensus / transcript / guidance tables are missing, show empty state + “requires ERDP-0x” instead of fabricating metrics.
4. **Deep-link to Company** — every row action opens Research Workspace (Company 360 ER tabs) for the CIK.
5. **No skill body rewrites** — optional later: financial-services docs *link* to these screens; out of scope here.
6. **Reuse existing triad** — Company 360 / Fundamentals Screener / Insider Watch remain P0 audit UIs; ER nav *extends* them.

---

## 4. Dashboard inventory (locked)

| ID | Name | ER skills (primary) | Priority | Data readiness today |
|----|------|---------------------|----------|----------------------|
| **ERD-1** | Earnings Desk | earnings-preview, earnings-analysis, model-update, morning-note (earnings flash) | **P0** | GAAP + calendar (03) + EOD (07); consensus/guidance/transcript **stub** |
| **ERD-2** | Catalyst Board | catalyst-calendar, morning-note (calendar half) | **P0** | ERDP-03 + filings; macro External |
| **ERD-3** | Research Workspace | initiating-coverage, model-update, thesis-tracker, earnings-analysis (history) | **P0** | Gold + graph + ERDP-07; thesis store N/A (local panel) |
| **ERD-4** | Idea & Sector Screen | idea-generation, sector-overview | **P0** | Factors + ERDP-07 multiples; consensus revisions **stub** |
| **ERD-5** | Thesis panel | thesis-tracker | **P1** (embedded in ERD-3) | User-entered pillars; platform evidence only |

No separate fifth top-level app for thesis in phase-1.

---

## 5. Global chrome (all ER screens)

```text
┌ Sidebar ──────────────────────────────────────────────────┐
│ Mode: (•) Agent View  ( ) Explore                         │
│ Banner: mode-specific (contract vs not-for-agent)         │
│ Nav: Summary | Company | Earnings | Catalysts | Ideas     │
│      | Pipeline                                           │
│ Context: Ticker/CIK search · coverage list (optional)     │
│ Watermark strip: business_date · contract version · lag   │
└───────────────────────────────────────────────────────────┘
```

| Element | Agent View | Explore |
|---------|------------|---------|
| Subject Feature Screen table | Yes | Yes |
| Subject Bundle sections | Yes | Yes |
| Free gold (`FINANCIAL_DERIVED`, `EARNINGS_RELEASES`, ownership, …) | **Blocked** | Yes |
| `EARNINGS_CALENDAR` (ERDP-03) | **Blocked** | Yes |
| ERDP-07 EOD (yfinance) | **Blocked** | Yes (label `source_system=yahoo`, `grade=explore`) |
| Future ERDP-01/02/04 | **Blocked** | Yes when published |
| Ops status lag | Yes (status object only) | Yes |

---

## 6. ERD-1 — Earnings Desk

### 6.1 Purpose

Single place for the **earnings cycle**: pre-print setup → post-print GAAP flash → estimate/model hooks → link-out to full note workflow.

### 6.2 Skill mapping

| Skill phase | UI zone |
|-------------|---------|
| **earnings-preview** | Pre-print panel: calendar session, prior financials, consensus stub, bull/base/bear scaffolding |
| **earnings-analysis** | Post-print: GAAP vs prior, history charts, transcript stub, valuation Explore |
| **model-update** | Actuals plug table from `EARNINGS_RELEASES` + `FINANCIAL_DERIVED`; PT/multiples via ERDP-07 |
| **morning-note** | Flash strip: beat/miss table when consensus available; else GAAP-only flash |

### 6.3 Layout

See [wireframes.md §ERD-1](./assets/wireframes.md#erd-1-earnings-desk).

### 6.4 Widgets → data

| Widget | Mode | Source | Empty state |
|--------|------|--------|-------------|
| Event header (FY/FQ, expected date, session) | Explore | `EARNINGS_CALENDAR` | “No forward calendar row — load ERDP-03” |
| GAAP flash (rev, NI, EPS) | Explore | `EARNINGS_RELEASES` | “No 8-K earnings parse for period” |
| History trends | Explore | `FINANCIAL_DERIVED` | — |
| Consensus vs actual | Explore | ERDP-01 `CONSENSUS_ESTIMATES` ⋈ release | **Stub** until ERDP-01 |
| Guidance vs actual | Explore | ERDP-02 `GUIDANCE_FACTS` | **Stub** until ERDP-02 |
| Transcript | Explore | ERDP-04 pointer | **Stub** until ERDP-04 |
| Spot / mcap / simple multiples | Explore | ERDP-07 + DERIVED | Live opt-in / cache |
| Agent bundle audit | Agent View | `SUBJECT_BUNDLE_READ` | Fail closed on watermark |

### 6.5 Interactions

- Select CIK → default to **latest calendar row** (upcoming or just reported).
- Toggle **Pre-print / Post-print** (status `estimated|confirmed` vs `reported`).
- **Export CSV** of actuals plug table (for Excel model-update skill).
- Deep-link **Open Research Workspace**.

### 6.6 Acceptance (design-level)

- A01: For a sample CIK with ERDP-03 row, pre-print panel shows date + session without consensus.
- A02: For a CIK with `EARNINGS_RELEASES`, post-print shows GAAP metrics + prior-period DERIVED context.
- A03: Agent View blocks calendar/price widgets; shows contract banner only.

---

## 7. ERD-2 — Catalyst Board

### 7.1 Purpose

Coverage-universe **forward calendar** + this-week list for morning meeting (skill: catalyst-calendar / morning-note calendar half).

### 7.2 Layout

See [wireframes.md §ERD-2](./assets/wireframes.md#erd-2-catalyst-board).

### 7.3 Widgets → data

| Widget | Mode | Source |
|--------|------|--------|
| Next N days earnings list | Explore | `EARNINGS_CALENDAR` (`next_n_days` recipe) |
| Session mix (BMO/AMC) | Explore | calendar `session` |
| Coverage filter | Explore | MDM tracked CIKs / user paste list |
| Reactive filings tape (8-K, 4) | Explore | `FILING_ACTIVITY`, `OWNERSHIP_ACTIVITY` |
| Macro / conferences | — | **External** — placeholder “not platform” |
| Price reaction (optional) | Explore | ERDP-07 last close only |

### 7.4 Acceptance

- B01: ≥10 universe CIKs → ≥80% have forward or just-reported calendar row (align ERDP-03 A03.1) or show measured coverage %.
- B02: Confirmed rows never display session=unknown (mirror normalize rules).

---

## 8. ERD-3 — Research Workspace (Company 360 + ER tabs)

### 8.1 Purpose

**One-issuer workspace** for initiation Tasks 1–3, ongoing model-update, thesis evidence, and earnings history. Extends existing Company Details rather than a parallel app.

### 8.2 Tabs (beyond generic 360)

| Tab | Skill affinity | Content |
|-----|----------------|---------|
| Overview | all | Identity, SIC, FYE, watermark, tracking |
| Filings | initiating T1 | Activity + accession deep links |
| Financials | initiating T2, model-update | Multi-year DERIVED + factors |
| Earnings history | earnings-analysis | Release tape + calendar history |
| Ownership / 13F | idea / initiation | Form 4 + holders bundle section |
| Flags & audit | initiation risk | `ACCOUNTING_FLAGS`, auditor edge |
| **Valuation Explore** | initiating T3, model-update | ERDP-07 close/mcap/beta, EV, WACC, simple multiples |
| **Thesis** | thesis-tracker | User pillars/risks (session or CSV upload); evidence chips from SEC events |
| Relationships | initiation | Bundle insiders / parent / employment |

### 8.3 Explicit non-goals

- Full Excel authoring (skills own xlsx).
- Street PT/rating history (External).
- Segment product/geo mart (OOS phase-1).

### 8.4 Acceptance

- C01: Explore Valuation tab computes EV for sample CIK when yfinance available (or mock path).
- C02: Agent View shows bundle + screen only; Valuation tab disabled with explanation.

---

## 9. ERD-4 — Idea & Sector Screen

### 9.1 Purpose

Multi-issuer **screen** for idea-generation and sector-overview valuation block. Extends Fundamentals Screener with optional Explore multiples.

### 9.2 Modes of use

| Recipe | Filters | Columns |
|--------|---------|---------|
| Pure-SEC quality | SIC, rev CAGR, ROIC, FCF, Beneish | Factor table (Agent View capable via Feature Screen) |
| Value Explore | + max EV/EBITDA, min FCF yield | Factors ⋈ ERDP-07 (Explore only) |
| Sector pack | SIC slice | Peer table + median multiples Explore |

### 9.3 Layout

See [wireframes.md §ERD-4](./assets/wireframes.md#erd-4-idea--sector-screen).

### 9.4 Acceptance

- D01: Agent View ranks via Feature Screen without prices.
- D02: Explore value recipe labels every multiple column `grade=explore`.
- D03: Row click → Research Workspace with CIK.

---

## 10. ERD-5 — Thesis panel (embedded)

Not a top-level nav item. Lives under Research Workspace.

| Field | Source |
|-------|--------|
| Pillars / risks / conviction | User input (session state or uploaded md/csv) |
| Evidence feed | Platform: latest earnings release, Form 4 clusters, 13F holder changes, accounting flags |
| PT vs spot | User/model PT + ERDP-07 spot (Explore) |

Platform does **not** become system of record for thesis text.

---

## 11. Skill coverage summary

Full matrix: [assets/skill-dashboard-map.md](./assets/skill-dashboard-map.md).

| Skill | Primary | Secondary |
|-------|---------|-----------|
| catalyst-calendar | ERD-2 | — |
| earnings-preview | ERD-1 pre-print | ERD-2 |
| morning-note | ERD-2 + ERD-1 flash | — |
| model-update | ERD-1 actuals + ERD-3 valuation | — |
| earnings-analysis | ERD-1 post-print + ERD-3 history | — |
| initiating-coverage | ERD-3 | ERD-4 peers |
| thesis-tracker | ERD-3 thesis panel | — |
| idea-generation | ERD-4 | Insider Watch (existing) |
| sector-overview | ERD-4 sector pack | ERD-3 peers |

---

## 12. Build order (implementation roadmap)

Aligned with [issues/03-build-order-vs-erdp.md](./issues/03-build-order-vs-erdp.md).

| Phase | Ship | Depends on |
|-------|------|------------|
| **P0a** | ERD-2 Catalyst Board (calendar list + coverage filter) | ERDP-03 code + gold |
| **P0b** | ERD-3 Valuation Explore tab + Thesis panel shell | ERDP-07 + existing Company Details |
| **P0c** | ERD-1 Earnings Desk shell (GAAP + calendar; stubs for 01/02/04) | gold releases + ERDP-03 |
| **P0d** | ERD-4 Idea screen Explore multiples recipe | ERDP-07 + factors |
| **P1** | Wire ERDP-01/02 panels when tables land | er-data-plane |
| **P1** | Transcript viewer when ERDP-04 lands | er-data-plane |
| **P2** | Promote durable docs under `docs/er-dashboards.md` | after SiS merge |

### SiS implementation notes

- Prefer extending `streamlit_app.py` (or multipage sibling modules staged with deploy).
- Reuse `_render_mode_chrome`, `_is_object_allowed`, gold query helpers.
- Mirror any new allowlist rules in `edgar_warehouse/serving/dashboard_modes.py` **only if** Agent View gains objects (prefer not).
- Unit tests: mode gating for new pages; no live Yahoo in default CI (opt-in flags like ERDP07_LIVE).

---

## 13. Relation to existing six dashboards

| Existing design | ER relation |
|-----------------|-------------|
| Platform Command Center | Unchanged — ops, not ER |
| Company 360 | **Becomes ERD-3** with extra tabs |
| Insider Watch | Shared by idea-generation / morning; keep separate nav |
| Institutional Positioning | Secondary for ER; not phase-1 ER primary |
| Fundamentals Screener | **Becomes ERD-4** base + Explore recipe |
| Adviser & Fund Explorer | Out of ER skill set |

---

## 14. Open risks

| Risk | Mitigation |
|------|------------|
| Consensus still missing → beat/miss incomplete | Explicit stubs; don’t fake Street numbers |
| yfinance flaky / ToS | Cache, batch guidance from ERDP-07 docs; grade=explore |
| Finnhub license for calendar commercial gold | Ops gate already on er-data-plane HANDOFF |
| Scope creep into skill rewrites | C-06: links only after products exist |
| Dual-mode bugs leak prices into Agent View | Architecture tests + allowlist |

---

## 15. Success criteria (design pack)

- [x] Four primary dashboards specified with layouts and data bindings
- [x] All nine ER skills map to a primary path
- [x] Mode × object matrix documented
- [x] Build order respects ERDP readiness (03/07 first)
- [x] No conflict with ADR 0001 / existing P0 audit triad

---

*End of design spec. Implementation starts with SiS nav tickets, not skill markdown.*
