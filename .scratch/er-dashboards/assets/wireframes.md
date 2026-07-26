# ER dashboard wireframes (ASCII)

Host: Streamlit-in-Snowflake · layout: `wide`  
All screens share mode chrome (sidebar).

---

## ERD-1 Earnings Desk

```text
┌─ Earnings Desk ──────────────────────────────────────────────────────────┐
│ CIK/Ticker [ AAPL ▼ ]   Period [ FY2025 Q3 ▼ ]   View: (•) Pre  ( ) Post │
│ Status: confirmed · after_close · expected 2025-07-31 · as_of 2025-07-01 │
├── KPIs ──────────────────────────────────────────────────────────────────┤
│ Expected session │ Days to print │ Last close* │ Mcap* │ FY rev (prior)  │
├── Left (inputs) ──────────────┬── Right (output scaffolding) ────────────┤
│ Prior DERIVED (rev, EPS, FCF) │ Consensus table [STUB ERDP-01]           │
│ Prior release GAAP            │ Guidance [STUB ERDP-02]                  │
│ Calendar history (last 8 q)   │ Bull / Base / Bear notes (user text)     │
│                               │ Metrics to watch checklist (user)        │
├── Post-print only ───────────────────────────────────────────────────────┤
│ GAAP flash: Rev · NI · EPS_diluted · filing_date · accession             │
│ Beat/miss vs consensus [STUB] │ vs prior guide [STUB]                    │
│ Transcript link [STUB ERDP-04]│ Valuation Explore: P/E, EV/EBITDA*       │
│ Actuals plug table → [Download CSV for model-update]                     │
├── Footer ────────────────────────────────────────────────────────────────┤
│ [Open Research Workspace]  [View Form 4 ±5d]  [Agent View: Bundle only]   │
└──────────────────────────────────────────────────────────────────────────┘
* Explore-only (ERDP-07)
```

---

## ERD-2 Catalyst Board

```text
┌─ Catalyst Board ─────────────────────────────────────────────────────────┐
│ Horizon: [7d] [14d] [30d]   Universe: (•) Tracked  ( ) Paste tickers     │
│ Session filter: [all] pre_market after_close                             │
├── KPIs: # earnings │ # confirmed │ # estimated │ coverage % ─────────────┤
├── This week (table) ─────────────────────────────────────────────────────┤
│ Date │ Session │ Ticker │ CIK │ FY/FQ │ Status │ Source │ [Open Desk]   │
├── Charts ──────────────────────┬── Reactive tape (Explore) ──────────────┤
│ Earnings by day (bar)          │ Recent 8-K / Form 4 for coverage list   │
│ BMO vs AMC mix (pie)           │ (not a substitute for forward calendar) │
├── Placeholders ──────────────────────────────────────────────────────────┤
│ Macro calendar: External · Conferences: External · IR events: future     │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## ERD-3 Research Workspace

```text
┌─ Research Workspace · AAPL · 0000320193 ─────────────────────────────────┐
│ Name · Exchange · SIC · FYE · Tracking · Watermark: OK / FAIL            │
│ KPI: Rev FY │ FCF │ Debt/Assets │ Insider 90d │ Last 10-K                │
├ Tabs: Overview | Filings | Financials | Earnings | Ownership | Flags     │
│       | Valuation Explore* | Thesis | Relationships                      │
├── Valuation Explore* ────────────────────────────────────────────────────┤
│ as_of [date]  Close*  Mcap*  Beta*  source=yahoo grade=explore           │
│ EV = mcap + debt − cash   │ WACC (helper) │ P/E · EV/EBITDA · FCF yield  │
│ Peer multiples table (SIC neighbors + EOD)*                              │
├── Thesis panel ──────────────────────────────────────────────────────────┤
│ Pillars (user) │ Risks (user) │ Conviction │ Model PT (user)             │
│ Evidence chips: last earnings · Form 4 cluster · flag change             │
│ Upside to PT vs spot*                                                    │
└──────────────────────────────────────────────────────────────────────────┘
* Explore-only
```

---

## ERD-4 Idea & Sector Screen

```text
┌─ Idea & Sector Screen ───────────────────────────────────────────────────┐
│ Recipe: (•) Pure-SEC quality  ( ) Value Explore*  ( ) Sector pack*       │
│ Filters: SIC [ ]  min rev  min ROIC  max debt/assets  max Beneish        │
│ Explore extras*: max EV/EBITDA  min FCF yield  as_of date                │
├── Results table (sortable) ──────────────────────────────────────────────┤
│ Ticker │ CIK │ Rev │ Rev CAGR 3y │ ROIC │ FCF/rev │ Flags │ EV/EBITDA* │
├── Side panel ────────────────────────────────────────────────────────────┤
│ Factor histogram │ Sector median multiples* │ [Open Research Workspace]  │
│ Banner if Value/Sector: Explore — not Trading Decision input             │
└──────────────────────────────────────────────────────────────────────────┘
* Explore-only columns hidden in Agent View (Feature Screen path only)
```

---

## Shared empty / stub component

```text
┌─────────────────────────────────────────────┐
│ ⚠ Panel unavailable                         │
│ Requires platform product: ERDP-0X · STATUS │
│ Skill can still proceed with user-supplied  │
│ data or external terminal.                  │
│ Doc: docs/er-*.md / .scratch/er-data-plane  │
└─────────────────────────────────────────────┘
```
