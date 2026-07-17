# Agent Decision Surface first (graph bundles over Snowflake)

**Status:** accepted  
**Ingest doctrine:** see [0002-silver-soe-edgartools-exclusive.md](0002-silver-soe-edgartools-exclusive.md) — agents still read **Snowflake only**; warehouse hot path is silver + edgartools, not default bronze.

The platform’s product output for trading is not a dashboard-first research app
and not an order-execution system. v1 prioritizes an **Agent Decision Surface**:
versioned, machine-readable **Decision Graph Bundles** delivered through a
**Snowflake Decision Contract**, so an automated agent can form **Trading
Decisions** outside this platform. Humans get **Human Audit Views** (including
Company 360, Fundamentals Screener, and Insider Watch) with explicit **Agent
View Mode** vs **Explore Mode**; Agent View Mode may only project the contract.

## Why

- Eventual consumer is a trading agent; UI shape is a poor primary contract.
- Multi-entity context (insiders, holdings, auditor, subject factors) requires a
  **Trading-Relevant Neighborhood**, not a single factor row.
- Reproducibility for trading requires a composite **Decision Watermark** and
  fail-closed **Agent-Grade Reads** when graph generation and gold features
  disagree.
- Pure-SEC accounting features stay inside the warehouse boundary; market prices
  join elsewhere.
- Product OAuth is deferred; the contract must stay pluggable behind later
  access control without reshaping features.

## Locked shape (v1)

| Concern | Decision |
| --- | --- |
| Unit of read | Decision Graph Bundle rooted at Bundle Subject (CIK) |
| Neighborhood | Trading-Relevant: insiders/employment, holdings when present, auditor when present, subject features |
| Edge currency | Current Neighborhood default; Neighborhood History optional |
| Factors | As-Of Decision Features: Primary Annual (FY) + Latest Interim if newer; historic series only as calc inputs; null ≠ zero |
| Holdings “current” | Latest Complete Holdings Period (13F lag exposed in coverage) |
| Partial data | Bundle Coverage Flags (present / empty / unavailable) |
| Delivery | Snowflake Decision Contract |
| Multi-subject | Subject Feature Screen + Subject Bundle Read |
| Universe | Decision Subject Universe = tracked/active only |
| Market data | Pure-SEC Decision Features only |
| Auth | Deferred Access Control (OAuth after go-live) |
| Versioning | Decision Contract Version on every payload |
| Mismatch | No Agent-Grade Read if watermark components misaligned |

## Considered options (rejected for v1)

- **UI-first / dashboard as source of truth** — rework when the agent lands; dual truth.
- **Single-row company features only** — underuses graph and multi-entity signal.
- **Full relationship registry or ADV-first bundles** — blocked on completeness gates.
- **Prices inside the contract** — expands trust boundary and pipeline before go-live.
- **Best-effort joins without watermark alignment** — unsafe for trading inputs.
- **OAuth-gated v1** — delays go-live; access layer should plug in later.

## Consequences

- Spec and tickets should lead with contract objects, watermark alignment, and
  coverage semantics; Streamlit work is secondary and mode-labeled.
- Graph generation freshness is on the critical path for Agent-Grade Reads, not
  optional polish.
- Agents must pin Decision Contract Version and handle partial coverage /
  abstain; the platform does not place trades.
- Explore Mode may use free gold SQL but must never be presented as what the
  agent saw.

Glossary: `CONTEXT.md` (Agent decision support section).
Product decision table: `docs/product-questions-and-dashboards.md`.
