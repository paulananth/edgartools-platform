# ER skill × dashboard coverage map

**Rule:** Every skill has exactly one **primary** dashboard path and optional secondaries.  
**Legend:** P = primary · S = secondary · — = not this skill’s surface

| ER skill | ERD-1 Earnings Desk | ERD-2 Catalyst Board | ERD-3 Research Workspace | ERD-4 Idea & Sector | Existing Insider Watch |
|----------|:-------------------:|:--------------------:|:------------------------:|:-------------------:|:----------------------:|
| catalyst-calendar | S (event detail) | **P** | — | — | — |
| earnings-preview | **P** (pre-print) | S | S (history) | — | — |
| morning-note | S (flash table) | **P** (week list) | — | — | S |
| model-update | **P** (actuals plug) | — | **P** (valuation) | — | — |
| earnings-analysis | **P** (post-print) | — | S (history/flags) | — | — |
| initiating-coverage | S (earnings hist) | — | **P** | S (peers) | S |
| thesis-tracker | — | S (upcoming) | **P** (panel) | — | — |
| idea-generation | — | — | S (drill-in) | **P** | S |
| sector-overview | — | — | S (peer co) | **P** | — |

---

## Skill I/O → dashboard widgets (summary)

| Skill | Critical inputs (from er-skills-io) | Dashboard supplies today | Still external / stub |
|-------|-------------------------------------|--------------------------|------------------------|
| catalyst-calendar | Universe, horizon, event types | Calendar gold, filing tape | Macro, conferences |
| earnings-preview | Company, quarter, consensus, date/time, guide | Calendar, prior DERIVED, EOD setup | Consensus, guidance values, options |
| morning-note | Overnight news, coverage, consensus vs actual | Calendar, 8-K/Form4 tape, price Explore | News wire, ratings, consensus |
| model-update | Model file, actuals, guide, macro | GAAP + DERIVED export; EOD PT math | Model file (user), guidance, consensus |
| earnings-analysis | Release, 10-Q, transcript, consensus | GAAP flash, filings links, history, EOD val | Transcript, consensus, IR deck |
| initiating-coverage | Ticker, filings, financials | Full 360 + valuation Explore | TAM/competitors, Excel authoring |
| thesis-tracker | Pillars, risks, new data point | Evidence chips + PT vs spot | Thesis SoR (user) |
| idea-generation | Screen criteria, universe | Factors + Explore multiples | Short interest, consensus revisions |
| sector-overview | Sector scope, peers, multiples | SIC slice + multiples Explore | Industry narrative / TAM |

---

## Desk workflow → screen sequence

```text
Daily
  Catalyst Board (this week) → optional Morning flash on Earnings Desk

Pre-earnings
  Catalyst Board (event) → Earnings Desk pre-print → Research Workspace model check

Post-earnings
  Earnings Desk post-print → export actuals → model-update skill offline
  → Research Workspace valuation Explore → Thesis panel update
  → earnings-analysis skill for DOCX (transcript when ERDP-04)

Initiation / franchise
  Idea & Sector Screen → Research Workspace tabs 1…n → offline report skills

Ideas
  Idea & Sector Screen (pure-SEC or value Explore) → Research Workspace → thesis seed
```
