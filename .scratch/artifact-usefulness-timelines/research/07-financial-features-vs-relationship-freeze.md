# Research: Financial feature history is not relationship freeze

**Ticket:** [07-financial-feature-history-not-relationship-freeze](../issues/07-financial-feature-history-not-relationship-freeze.md)  
**Sources:** `CONTEXT.md` (As-Of Decision Features; Pure-SEC Decision Features), [ADR 0001](../../../docs/adr/0001-agent-decision-surface-first.md), [decision-watermark.md](../../../docs/decision-watermark.md) / `edgar_warehouse.serving.decision_contract`, [agent-and-research-source-relevance-windows.md](../../../docs/release-readiness/agent-and-research-source-relevance-windows.md), [subject-feature-screen.md](../../../docs/subject-feature-screen.md), dbt `financial_factors` / `cagr` macro.

## Question restated

What multi-year history do CAGR / growth / earnings-potential style **As-Of Decision Features** require, and which pipeline supplies it — proving it must **not** drive Ticket 20 relationship document windows?

## Doctrine split (do not confuse)

| Concept | What the agent needs | Pipeline | Ticket 20 bulk-load? |
| --- | --- | --- | --- |
| **Investment analysis features** (CAGR, growth, earnings-potential style factors) | One **as-of feature row** at watermark `W` whose **inputs** may span multi-year FY history | **Companyfacts → silver financial facts → gold / dbt Decision Features** (Subject Feature Screen) | **No** |
| **Relationship / event sources** | Current-at-watermark edges + declared relationship lookbacks | Proxy, Item 5.02 8-K, 13F, ownership, ADV via freeze + MDM/graph | **Yes** — separate windows |
| **Human Explore** | Broader browsing | Same warehouse tables, labeled non-agent-grade | Optional deeper archives |

**Locked grill decision (#3):** CAGR / growth come from **companyfacts → gold features**, **not** from loading deep 13F or 8-K history.

Implication (platform doctrine):

> Loading less 8-K or less 13F history does **not** break 3y/5y CAGR.  
> CAGR needs multi-year **financial** facts, not multi-year Item 5.02 filings.

## Feature input lookbacks

Per ADR 0001 and CONTEXT **As-Of Decision Features**:

- Inputs **may** be multi-period history (e.g. **3y / 5y CAGR**, YoY growth).
- The **published** feature is still a **single current as-of view** at `W`.
- **null ≠ zero** when history is insufficient under declared rules.
- Agent **must not** recompute CAGR from raw filings for v1; it reads published factors.

Gold implementation (`infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` + `macros/cagr.sql`):

| Feature class | Input span | Published shape |
| --- | --- | --- |
| `revenue_cagr_3y`, `net_income_cagr_3y`, `total_assets_cagr_3y` | Current FY vs FY **3 years** prior | Columns on as-of factor row |
| `revenue_cagr_5y`, `net_income_cagr_5y`, `total_assets_cagr_5y` | Current FY vs FY **5 years** prior | Columns on as-of factor row |
| Other ratios / liquidity / leverage | Latest complete FY (+ optional newer interim) | Same as-of row / interim vector |

**Required financial history for agent-grade features:** enough **companyfacts / FY period rows** to satisfy declared 3y and 5y CAGR rules (and interim rules for Latest Interim Feature Vector). That history lives in the **fundamentals / entity-facts** path, not in relationship artifact freezes.

## Pipeline that supplies multi-year financial inputs

```text
SEC companyfacts API (per CIK)
  → edgartools gateway / entity-facts (silver-once: CIK + facts_parser_version)
  → silver sec_financial_fact (and related)
  → gold / dbt FINANCIAL_FACTORS (CAGR macros, ratios)
  → Snowflake Decision Contract
       • Subject Feature Screen (ticket 10)
       • subject_features on Subject Bundle Read (ticket 11)
  → Decision Watermark: gold_run_id + business_date + graph_generation_id + completeness flags
```

Code / doc pointers:

| Layer | Location |
| --- | --- |
| Gateway | `edgar_warehouse/infrastructure/edgartools_sec_gateway.py` (`fetch_companyfacts_json`) |
| Parse | `edgar_warehouse/parsers/financials.py` |
| Ingest | `edgar_warehouse/application/workflows/fundamentals_ingest.py` |
| Silver-once | agent-decision-data-plane issue 04 |
| Gold CAGR | `infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql` |
| Contract | `edgar_warehouse/serving/subject_feature_screen.py`, `decision_contract.py` |
| Watermark | `docs/decision-watermark.md` |

ADR 0002 / silver SoE: agent-grade financial readiness does **not** require mandatory companyfacts bronze by default; silver + published gold/features are the agent path.

## Explicit non-dependency on 13F / 8-K bulk-load depth

| Relationship load choice | Effect on 3y/5y CAGR features |
| --- | --- |
| 13F only last **3y** (not full XML-era to 2013) | **None** on CAGR correctness |
| Item 5.02 8-K only last **1y** | **None** |
| Proxy baseline + **5y** | **None** |
| Deeper Explore archives for 13F/8-K | **None** — still orthogonal |

Ticket 20 denominators and relationship GO claims must **not**:

- use “need 5y CAGR” as a reason to load 5y of 8-Ks or full 13F since 2013;
- couple `silver_completeness_ok` for **relationship** freezes to financial FY depth (or the reverse) without separate completeness claims;
- put companyfacts accessions into the relationship bulk-load completion ledger as if they were DEF 14A / 13F candidates.

Financial completeness is a **feature / gold_run** concern under the Decision Watermark, not a relationship freeze window.

## What Ticket 20 must / must not own

**Must own (relationship windows only):** 13F, proxy, Item 5.02 8-K (and other registered relationship sources) under per-type lookbacks.

**Must not own:** companyfacts multi-year FY series, CAGR calculation, Subject Feature Screen factor completeness.

Optional deeper relationship archives remain a **later / separate** Explore pipeline — still unrelated to CAGR.

## Exit criteria map

| Criterion | Answer |
| --- | --- |
| Feature input lookbacks | **3y / 5y FY** inputs for CAGR-style factors; published as one as-of row at `W`. |
| Pipeline | **Companyfacts → silver → gold/dbt `financial_factors` → Decision Contract**. |
| Non-dependency | CAGR **does not** require deep 13F or 8-K bulk-load; Ticket 20 must not encode financial history. |
| Pointers | ADR 0001, CONTEXT As-Of Decision Features, decision_contract / watermark, agent-and-research-source-relevance-windows. |

## Downstream effect on lock tickets

Tickets **08 / 09 / 10** (lock 13F, Item 5.02 8-K, proxy agent windows) may freeze relationship lookbacks **without** reopening financial history. Ticket 07 is the explicit firewall: multi-year financial inputs stay on the features pipeline.

## Related

- [05-proxy-usefulness.md](./05-proxy-usefulness.md) — relationship, not features  
- [06-ownership-form345-usefulness.md](./06-ownership-form345-usefulness.md) — insider activity, not CAGR  
- Grill log row 3 in agent-and-research-source-relevance-windows (CAGR vs relationship load = locked)
