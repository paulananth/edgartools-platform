# ERDP-01 — Consensus Estimates (Detailed Product Spec)

| Field | Value |
|-------|--------|
| **ID** | ERDP-01 |
| **Name** | Consensus estimates |
| **Status** | Spec ready for design/build planning (not implemented) |
| **Pilot source_system** | **`yahoo`** (primary); **`firm_manual`** (fallback) |
| **Alternate free pilot** | `fmp` (optional; rate-limited) |
| **Milestone** | ER data plane phase-1 |
| **REQUIREMENTS** | `.planning/workstreams/er-data-plane/REQUIREMENTS.md` (ERDP-01-*) |
| **Parent plan** | `.scratch/er-data-plane/spec.md` |
| **Schema sketch** | `.scratch/er-data-plane/assets/erdp-01-04-schema-sketches.md` § ERDP-01 |
| **Free sources research** | `.scratch/er-data-plane/assets/free-data-sources-erdp-01-04.md` |
| **Consumers** | `earnings-preview`, `earnings-analysis`, `morning-note`, `model-update` (secondary), `idea-generation` (light) |
| **Layer** | **Gold Explore** SoR; optional MDM keys; **not** graph; **not** pure-SEC Agent-Grade features |

---

## 1. Problem statement

ER skills need **Street (or proxy) consensus** for revenue, EPS, and related metrics, with a known **as-of date**, to:

- Build pre-print **earnings-preview** frameworks  
- Compute **beat/miss** vs actuals in earnings notes and morning notes  
- Contextualize estimate revisions in **model-update**

The platform today has **actuals** (`FINANCIAL_DERIVED`, `EARNINGS_RELEASES`) but **no consensus table**. Free/pilot sources (Yahoo, FMP, Estimize) can feed a vendor-agnostic schema; institutional IBES-quality is optional later via another `source_system`.

---

## 2. Goals and non-goals

### Goals

1. Persist **multi-metric consensus** by issuer, fiscal period, and **as_of** snapshot.  
2. Support **statistics** (mean/median/high/low/n_analysts/stdev), not only a single number.  
3. Retain **history** of as_of dates (no silent overwrite).  
4. Stay **provider-agnostic** (`source_system` required).  
5. Enable join to identity (CIK/ticker) and to actuals for beat/miss.  
6. Remain **Explore-only** (ADR 0001).

### Non-goals

| Out | Elsewhere |
|-----|-----------|
| Company-issued **guidance** | ERDP-02 |
| Earnings **calendar** | ERDP-03 |
| Price targets / ratings | External / deferred |
| Market prices | External (ERDP-06) |
| Inject into `subject_features` | Forbidden without ADR |
| Neo4j edges | Out of phase-1 |
| Guaranteeing IBES-grade free data | Pilot free; production may pay |

---

## 3. User stories

1. **As** `earnings-preview`, I need NTM/quarterly consensus rev/EPS for ticker T as of today.  
2. **As** `earnings-analysis`, I need consensus **as_of ≤ print date** for the reported quarter to compute beat/miss.  
3. **As** `morning-note`, I need a quick consensus vs actual table after a print.  
4. **As** ops, I need to load firm CSV when no vendor API is licensed.

---

## 4. Data product definition

### 4.1 Conceptual model

One row = one **consensus statistic** for:

- issuer (`cik`)
- `metric`
- fiscal / forward period (`period_type`, FY/FQ)
- `statistic` (mean, median, …)
- snapshot date `as_of`
- `source_system`

### 4.2 Grain and natural key

```text
(cik, metric, period_type, fiscal_year, fiscal_quarter, statistic, as_of, source_system)
```

| Rule | Encoding |
|------|----------|
| Annual | `fiscal_quarter = 0` |
| NTM / LTM | `period_type` = `ntm`/`ltm`; FY/FQ null or 0 as documented |
| Point estimate only from vendor | Emit `statistic=mean` (or `median` if vendor only has median) |
| High/low | Separate rows with `statistic=high` / `low` |

**Surrogate:** `fact_key` = hash of natural key.

### 4.3 Relationship to actuals

```text
CONSENSUS_ESTIMATES (as_of ≤ print_date)
    ⋈  EARNINGS_RELEASES or FINANCIAL_DERIVED (actuals)
    →  beat/miss at query time (not stored)
```

Do **not** store beat/miss in this table (avoids coupling to actuals pipeline).

---

## 5. Logical schema (normative)

### 5.1 Names

| Layer | Name |
|-------|------|
| Silver (suggested) | `sec_consensus_estimate` or `ext_consensus_estimate` (non-SEC origin) |
| Gold export | `CONSENSUS_ESTIMATES` |
| dbt Gold | `EDGARTOOLS_GOLD.CONSENSUS_ESTIMATES` |

### 5.2 Columns

| Column | Type | Null | Description |
|--------|------|:----:|-------------|
| `fact_key` | int64 | N | Surrogate |
| `cik` | int64 | N | Issuer |
| `ticker` | string | Y | Denormalized |
| `company_key` | int64 | Y | Optional dim/MDM |
| `metric` | string | N | Controlled vocab §6 |
| `period_type` | string | N | `annual` \| `quarterly` \| `ntm` \| `ltm` \| `other` |
| `fiscal_year` | int32 | Y | |
| `fiscal_quarter` | int32 | Y | 1–4 or **0** annual |
| `period_end` | date | Y | When known |
| `estimate_value` | float64 | N | Value for this statistic |
| `unit` | string | N | `USD`, `USD_millions`, `per_share`, … |
| `currency` | string | Y | ISO 4217 |
| `statistic` | string | N | `mean` \| `median` \| `high` \| `low` \| `stdev` \| `n_analysts` |
| `as_of` | date | N | Snapshot date (**required**) |
| `source_system` | string | N | `yahoo` \| `fmp` \| `finnhub` \| `estimize` \| `factset` \| `bloomberg` \| `cap_iq` \| `firm_manual` \| `other` |
| `source_ref` | string | Y | Provider id |
| `ingested_at` | timestamp | N | UTC |

### 5.3 Integrity

1. `estimate_value` non-null.  
2. `as_of` non-null.  
3. `statistic=n_analysts` → value is count (non-negative integer stored as float ok).  
4. No price/mcap/PE/EV columns.  
5. Multi-`as_of` history retained for same period (A01.2).

---

## 6. Controlled vocabularies

### 6.1 Metrics (phase-1 minimum)

Must: `revenue`, `eps_diluted`.  
Should: `ebitda`, `net_income`, `eps_basic`, `gross_profit`.

### 6.2 Units

Same family as ERDP-02: `USD`, `USD_millions`, `per_share`, `ratio`, `percent`, `other`.  
Store as-reported; optional normalize view later.

---

## 7. Source and ingestion

### 7.1 Pilot free paths (see free-data research)

| source_system | Notes |
|---------------|--------|
| `yahoo` | yfinance / unofficial; fragile; good prototype |
| `fmp` | Free tier rate limits; check commercial ToS |
| `estimize` | Crowdsourced ≠ sell-side |
| `firm_manual` | CSV/Parquet drop |

### 7.2 Production path

Paid Street feed (`factset`, `bloomberg`, `cap_iq`) as additional `source_system` without schema change.

### 7.3 Pipeline sketch

```text
Vendor API or firm file
  → normalize to logical schema
  → validate + quarantine
  → silver upsert
  → gold export / dbt CONSENSUS_ESTIMATES
```

**Legal:** Free-tier redistribution into Snowflake may be restricted — ops must confirm ToS before production gold load.

### 7.4 Identity resolution

Map vendor ticker → CIK via `TICKER_REFERENCE` / MDM. Rows that fail CIK resolution go to quarantine (do not publish orphan tickers without CIK if requirement is CIK-not-null).

---

## 8. Query patterns

### 8.1 Current consensus (latest as_of)

```sql
SELECT *
FROM EDGARTOOLS_GOLD.CONSENSUS_ESTIMATES
WHERE cik = ? AND metric = 'eps_diluted'
  AND period_type = 'quarterly'
  AND fiscal_year = ? AND fiscal_quarter = ?
  AND statistic = 'mean'
QUALIFY ROW_NUMBER() OVER (PARTITION BY source_system ORDER BY as_of DESC) = 1;
```

### 8.2 Pre-print consensus for beat/miss

```sql
SELECT *
FROM EDGARTOOLS_GOLD.CONSENSUS_ESTIMATES
WHERE cik = ?
  AND metric IN ('revenue', 'eps_diluted')
  AND statistic = 'mean'
  AND as_of <= ?   -- print date
  AND fiscal_year = ? AND fiscal_quarter = ?
ORDER BY as_of DESC;
```

### 8.3 Explore vs Agent-Grade

Explore SQL only; never inject into pure-SEC feature vectors.

---

## 9. Acceptance criteria

| ID | Criterion |
|----|-----------|
| **A01.1** | Sample CIK: ≥1 row each for `eps_diluted` and `revenue` for latest completed FQ with non-null `as_of`. |
| **A01.2** | Two different `as_of` for same period both retained. |
| **A01.3** | Docs: Explore / not Agent-Grade. |
| **A01.4** | Sample rows join to COMPANY/TICKER_REFERENCE on cik. |
| **A01.5** | Doc recipe for beat/miss with EARNINGS_RELEASES + as_of ≤ print. |
| **A01.6** | firm_manual CSV round-trip for 1 CIK. |
| **A01.7** | Free-pilot path documented with ToS caveat (yahoo/fmp). |

---

## 10. REQUIREMENTS checklist

- [ ] ERDP-01-01 … 01-05 from milestone file  
- [ ] A01.2 / A01.6 / A01.7 as above  
- [ ] Schema registry + export + dbt  
- [ ] Quarantine for unresolved CIK  

---

## 11. Open design decisions

| # | Decision | Default |
|---|----------|---------|
| D1 | Pilot source | **Locked: `yahoo` primary; `firm_manual` fallback; optional `fmp`** |
| D2 | NTM encoding | period_type=ntm; FY/FQ=0 |
| D3 | Multi-source coexistence | Key includes source_system |
| D4 | Minimum history depth | Best-effort free; paid for deep as_of; A01.2 may be waived/best-effort on free pilot |

### 11.1 Pilot source lock (2026-07-25)

| Role | source_system | Notes |
|------|---------------|--------|
| Primary | `yahoo` | Aligns with ERDP-07 yfinance stack; unofficial API risk |
| Fallback | `firm_manual` | CSV/Parquet for demo CIKs |
| Optional | `fmp` | Free tier ~250 calls/day; ToS check for gold load |
| Production later | `factset` / `bloomberg` / `cap_iq` | Schema unchanged |

---

## 12. Traceability

| Artifact | Path |
|----------|------|
| Parent / REQs / free sources | `.scratch/er-data-plane/` |
| ER skills | `assets/er-skills-io.md` |
| ADR | `docs/adr/0001-agent-decision-surface-first.md` |

---

*Spec version 1.0 — planning; not implemented.*
