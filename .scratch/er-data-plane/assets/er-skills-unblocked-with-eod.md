# ER skills unblocked by free EOD prices (yfinance)

**Decision:** Pilot EOD = Yahoo / `yfinance` via `PriceProvider` (External Explore join).  
**ADR 0001:** Prices stay **out** of pure-SEC Decision Features / Agent-Grade `subject_features`.  
**Scope expansion:** Market join is first-class **Explore** capability **ERDP-07** (not a Street data product).

---

## 1. Skill × price impact

| ER skill | Needs price? | What EOD unblocks | Still blocked without |
|----------|:------------:|-------------------|------------------------|
| **catalyst-calendar** | Low | Optional: price reaction context on events | ERDP-03 calendar for forward earnings dates |
| **earnings-preview** | **Medium** | **Trading setup**: recent price, % move, mcap; rough implied reaction framing | Consensus (ERDP-01), calendar (ERDP-03), options still External |
| **morning-note** | **Medium** | Overnight/pre-market **price moves**; upside/downside to a **model PT** | Street ratings; consensus for beat/miss table; news wire |
| **model-update** | **High** | **P/E, EV/EBITDA, DCF fair value, price target** refresh after actuals | Excel model file (N/A); guidance values (ERDP-02); consensus (ERDP-01) for Street compare |
| **earnings-analysis** | **High** | Valuation section, price charts, upside to PT, multiple charts | Transcript (ERDP-04); consensus as_of (ERDP-01); IR deck |
| **initiating-coverage** | **High** | **Task 3:** WACC, EV, trading comps multiples, DCF → PT; price charts (Task 4) | Segment mart; full Excel still skill-built; Street PT history |
| **thesis-tracker** | **Medium** | Target price vs spot; upside %; invalidation on price levels | Thesis store (N/A); qualitative pillars |
| **idea-generation** | **High** | Value screens: earnings yield, FCF yield, EV/EBITDA cheap vs peers | Consensus revisions; short interest |
| **sector-overview** | **High** | Sector trading multiples, relative valuation charts | Competitive narrative / TAM (External) |

---

## 2. Readiness tiers (with gold + yfinance EOD)

### Tier A — Largely runnable for valuation/price-aware outputs

| Skill | Platform + EOD coverage |
|-------|-------------------------|
| **model-update** (valuation half) | Gold actuals + WACC/multiples/PT |
| **initiating-coverage Task 3** | FCF history + WACC + comps multiples |
| **idea-generation** (value screens) | Factors + price → yields/multiples |
| **sector-overview** (valuation block) | Peer DERIVED + prices → multiples |
| **thesis-tracker** (PT vs spot) | Spot + user/model PT |

### Tier B — Materially improved, not fully “complete skill”

| Skill | Unblocked piece | Still missing for full skill |
|-------|-----------------|------------------------------|
| **earnings-analysis** | Valuation / price charts | Transcript, consensus, full narrative |
| **earnings-preview** | Trading setup / mcap | Consensus, calendar, guide |
| **morning-note** | Price action | Ratings, consensus, news |

### Tier C — Little change from price alone

| Skill | Why |
|-------|-----|
| **catalyst-calendar** | Needs dates more than prices |
| Core of **earnings-preview** without Street bar | Still need consensus/calendar |

---

## 3. Models newly practical (gold + EOD)

| Model | Gold | EOD |
|-------|------|-----|
| WACC | debt, tax, interest | mcap, beta (+ FRED rf) |
| EV / equity value | cash, debt, shares | price → mcap |
| Trading comps | peer financials | peer prices |
| Simple DCF | FCF history | WACC |
| P/E, EV/EBITDA, FCF yield | EPS, EBITDA, FCF | price |
| PT sensitivity | — | spot + fair value |
| Value screens | factors | multiples/yields |

---

## 4. What price does **not** replace

| Still need | Why |
|------------|-----|
| ERDP-01 consensus | Beat/miss vs Street |
| ERDP-02 guidance | vs company guide |
| ERDP-03 calendar | When does it print |
| ERDP-04 transcript | Call narrative |
| Street ratings | Not computable from EOD alone |
| Options / implied move | Separate External |
| Excel model path | User workspace |

---

## 5. Scope expansion summary

| Before (phase-1) | After (scope expand) |
|------------------|----------------------|
| Market prices = External, not a product | **ERDP-07**: documented **Explore market join** via yfinance / `PriceProvider` |
| Pure-SEC only for Agent-Grade | **Unchanged** — prices never in `subject_features` |
| Valuation skills “blocked” | Valuation **paths unblocked** for Explore/research agents |

---

*Companion to eod-price-source-decision.md and models-on-gold-mdm-neo4j.md.*
