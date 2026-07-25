# ERDP-02 — Guidance Facts (Detailed Product Spec)

| Field | Value |
|-------|--------|
| **ID** | ERDP-02 |
| **Name** | Guidance facts |
| **Status** | Spec ready for design/build planning (not implemented) |
| **Milestone** | ER data plane phase-1 |
| **REQUIREMENTS** | `.planning/workstreams/er-data-plane/REQUIREMENTS.md` (ERDP-02-*) |
| **Parent plan** | `.scratch/er-data-plane/spec.md` |
| **Schema sketch** | `.scratch/er-data-plane/assets/erdp-01-04-schema-sketches.md` § ERDP-02 |
| **Consumers** | financial-services ER skills: `model-update`, `earnings-preview`, `earnings-analysis`, `morning-note` (secondary) |
| **Layer** | **Gold Explore** SoR; optional MDM `company_key`; **not** graph; **not** pure-SEC Agent-Grade features (ADR 0001 / ticket 03) |

---

## 1. Problem statement

Equity research workflows need **numeric company guidance** (e.g. full-year revenue $X–$Y, EPS $a–$b) to:

- Compare **actuals vs prior guide** after a print (`model-update`, earnings notes)
- Frame **preview** scenarios against management guide (`earnings-preview`)
- Explain beat/miss vs “company’s own bar,” not only Street consensus (ERDP-01)

Today the platform:

| Surface | Capability |
|---------|------------|
| `sec_earnings_release` / gold `EARNINGS_RELEASES` | Detects guidance **presence** (`has_guidance` boolean) via edgartools `EarningsRelease.guidance` |
| Silver schema note | Explicitly **defers** revenue/EPS guidance ranges and non-GAAP detail to a future extractor |

**ERDP-02** delivers those **values** as a first-class gold table, without putting guidance into pure-SEC Decision Feature vectors.

---

## 2. Goals and non-goals

### Goals

1. Persist **structured guidance facts** linked to identity (CIK) and preferably SEC accession.
2. Support **point** and **range** guidance (low / mid / high).
3. Support **GAAP vs non-GAAP** flagging at the metric level (`is_non_gaap`).
4. Support **as-of** (when guidance was given) so agents can reconstruct “guide in force before print.”
5. Prefer **SEC-derived** rows; allow **firm_manual** override/supplement.
6. Remain **Explore-only** (not Agent-Grade pure-SEC features).

### Non-goals (this product)

| Out | Owner / elsewhere |
|-----|-------------------|
| Street **consensus** estimates | ERDP-01 |
| Full non-GAAP P&L rebuild / every adjusted metric | Future / optional enrichment |
| Price targets or ratings | External |
| Injecting guidance into `subject_features` | Forbidden without new ADR |
| Neo4j edges for “issued guidance” | Out of phase-1 |
| Rewriting ER skill markdown | financial-services later |
| Guaranteeing 100% of US filers have extractable numeric guidance | Best-effort SEC parse + coverage metrics |

---

## 3. User stories (agent / analyst)

1. **As** `model-update`, **I need** prior-quarter or prior-FY company guide for revenue/EPS **so that** I can write “vs company guide” and revise forward estimates.
2. **As** `earnings-preview`, **I need** latest guide for the upcoming print period **so that** bull/base/bear can reference management’s bar.
3. **As** `earnings-analysis`, **I need** guide ranges from the related 8-K accession **so that** the note cites primary-source guidance with a filing link.
4. **As** a data agent, **I need** Explore SQL on `GUIDANCE_FACTS` **without** claiming Agent-Grade Decision Contract membership.

---

## 4. Data product definition

### 4.1 Conceptual model

One row = one **guidance observation** for:

- one issuer (`cik`)
- one **metric** (controlled vocabulary)
- one **guided period** (FY/FQ or annual)
- one **as-of** date (when guidance was issued/confirmed)
- one **GAAP vs non-GAAP** flag
- optionally one **SEC accession**

Values may be:

- **Point:** only `value_mid` (or only low=high=mid)
- **Range:** `value_low` and `value_high` (mid optional = midpoint)
- **Open-ended:** e.g. “at least $X” → low set, high null (document convention)

### 4.2 Relationship to existing earnings release

```text
8-K HTML (bronze)
    → earnings_release parser
         → sec_earnings_release (GAAP actuals + has_guidance flag)  [today]
         → NEW: guidance extractor → sec_guidance_fact (silver) → GUIDANCE_FACTS (gold)

Optional:
firm CSV/S3 drop → firm_manual loader → same gold table
```

- **Do not remove** `has_guidance` from `EARNINGS_RELEASES`.
- **Invariant (soft):** when gold has ≥1 `GUIDANCE_FACTS` row for an accession, corresponding `EARNINGS_RELEASES.has_guidance` should be true for that accession when an earnings release row exists.
- Guidance may exist **without** a full earnings release row (e.g. 10-Q outlook, 8-K Item 2.02 without full ER table parse).

### 4.3 Grain and keys

**Recommended natural key:**

```text
(cik, metric, fiscal_year, fiscal_quarter, as_of, accession_number, is_non_gaap, source_system)
```

Encoding rules:

| Situation | Encoding |
|-----------|----------|
| Annual guidance | `fiscal_quarter = 0` or NULL consistently (pick one; **recommend 0** for key stability) |
| Point guidance | set `value_mid`; low/high null **or** low=mid=high |
| No accession (firm_manual) | `accession_number = ''` empty string in key, not SQL NULL (or use sentinel) |
| Multiple guides same day same metric | Prefer latest parser_version; or include `value_mid` in key only if collisions proven |

**Surrogate:** `fact_key` = deterministic hash of natural key (same pattern as other gold facts).

---

## 5. Logical schema (normative)

### 5.1 Table names

| Layer | Name |
|-------|------|
| Silver (suggested) | `sec_guidance_fact` |
| Gold export / SOURCE | `GUIDANCE_FACTS` |
| dbt Gold (preferred agent SQL) | `EDGARTOOLS_GOLD.GUIDANCE_FACTS` |

### 5.2 Columns

| Column | Type | Null | Description |
|--------|------|:----:|-------------|
| `fact_key` | int64 | N | Deterministic surrogate |
| `cik` | int64 | N | Issuer CIK (no leading zeros) |
| `ticker` | string | Y | Primary ticker at ingest (denormalized aid) |
| `company_key` | int64 | Y | Optional link to company dim / MDM |
| `accession_number` | string | Y | SEC accession when SEC-sourced |
| `metric` | string | N | Controlled vocab — see §6 |
| `period_type` | string | N | `annual` \| `quarterly` \| `range_fy` \| `other` |
| `fiscal_year` | int32 | Y | Guided fiscal year |
| `fiscal_quarter` | int32 | Y | 1–4; **0** for annual |
| `period_end` | date | Y | Period end if known |
| `value_low` | float64 | Y | Range low (same unit as mid/high) |
| `value_mid` | float64 | Y | Point estimate or midpoint |
| `value_high` | float64 | Y | Range high |
| `unit` | string | N | See §6.2 |
| `currency` | string | Y | ISO 4217 when monetary; default USD when applicable |
| `is_non_gaap` | bool | N | Default false |
| `as_of` | date | N | Date guidance was given (usually filing date) |
| `source_system` | string | N | `sec_8k` \| `sec_10q` \| `sec_10k` \| `firm_manual` \| `other` |
| `source_ref` | string | Y | Exhibit name, paragraph id, firm row id |
| `excerpt` | string | Y | Optional short quote for audit (≤500 chars) |
| `confidence` | string | Y | `high` \| `medium` \| `low` (parser self-score) |
| `parser_version` | string | Y | When platform-parsed |
| `ingested_at` | timestamp | N | Load time UTC |

### 5.3 Integrity constraints

1. **At least one** of `value_low`, `value_mid`, `value_high` is non-null.  
2. If both low and high set: `value_low <= value_high`.  
3. If mid and both ends set: `value_low <= value_mid <= value_high` (when mid populated).  
4. `metric` ∈ controlled vocabulary or rejected to quarantine.  
5. `source_system` required.  
6. SEC-sourced rows **should** have `accession_number` (required for A02.1 sample path).  
7. **No** price, mcap, PE, EV columns (ERDP-06 / A06.1).

### 5.4 What is *not* in this table

- Beat/miss vs consensus (compute at query time with ERDP-01 + actuals).  
- Full non-GAAP actuals suite (separate future product if needed).  
- Narrative-only outlook without numbers (“expect strong growth”) — optional future `guidance_qualitative` or store only in excerpt with null values (default: **drop** pure qualitative).

---

## 6. Controlled vocabularies

### 6.1 Metrics (phase-1 minimum)

| `metric` | Meaning | Typical unit |
|----------|---------|--------------|
| `revenue` | Net sales / total revenue | `USD` or `USD_millions` |
| `eps_diluted` | Diluted EPS | `per_share` |
| `eps_basic` | Basic EPS | `per_share` |
| `ebitda` | EBITDA (often non-GAAP) | `USD` / `USD_millions` |
| `ebit` | Operating income / EBIT | `USD` / `USD_millions` |
| `net_income` | Net income | `USD` / `USD_millions` |
| `gross_profit` | Gross profit | `USD` / `USD_millions` |
| `operating_margin` | Op. margin | `ratio` (0.25 = 25%) or `percent` — **pick one; recommend ratio** |
| `free_cash_flow` | FCF | `USD` / `USD_millions` |
| `capex` | Capital expenditures | `USD` / `USD_millions` |
| `other` | Escaped with `source_ref`/excerpt | required unit free-text |

Phase-1 **must** support at least: `revenue`, `eps_diluted`. Others best-effort.

### 6.2 Units

| `unit` | Meaning |
|--------|---------|
| `USD` | Absolute US dollars |
| `USD_thousands` | $000s as reported |
| `USD_millions` | $mm as reported |
| `USD_billions` | $bn |
| `per_share` | Per diluted/basic share |
| `ratio` | Decimal fraction |
| `percent` | 0–100 scale (avoid mixing with ratio) |
| `shares` | Share count guidance (rare) |
| `other` | With note in source_ref |

**Normalization policy (recommended):** store **as reported** in source units; optional later gold view `GUIDANCE_FACTS_NORMALIZED` to USD. Phase-1 acceptance does not require USD normalization.

### 6.3 Period type

| `period_type` | Use |
|---------------|-----|
| `quarterly` | Guided Q1–Q4 |
| `annual` | Full fiscal year |
| `range_fy` | Multi-year or “FY25–FY26” style (fiscal_year = start year; document in excerpt) |
| `other` | Stub periods |

---

## 7. Source and ingestion design

### 7.1 Primary source: SEC (preferred)

| Form | Typical guidance location | `source_system` |
|------|---------------------------|-----------------|
| 8-K (Item 2.02 / EX-99.1) | Earnings release outlook section | `sec_8k` |
| 10-Q | MD&A outlook / liquidity | `sec_10q` |
| 10-K | Outlook / risk-adjacent forward statements | `sec_10k` |

**Reuse platform paths:**

- Bronze filing HTML already cached (same constraint as `earnings_release` parser: **no re-fetch** if bronze exists).  
- edgartools `EarningsRelease` already exposes `guidance` object for **presence**; ERDP-02 needs a **value extractor** (may extend edgartools usage or custom HTML/table/NLP rules).  
- Silver note in `silver_store.py` already anticipates guidance ranges as a future migration.

### 7.2 Secondary source: firm_manual

CSV/Parquet drop (S3 path TBD) with columns mapping 1:1 to logical schema (minimum subset).

Use cases: parser miss, private annotation, pilot before SEC extractor is robust.

### 7.3 Source priority / survivorship

When SEC parse and firm_manual conflict on same natural key:

| Rule | Choice (recommended) |
|------|----------------------|
| Same key | Prefer higher `confidence`, then newer `ingested_at` |
| Or | Keep both with different `source_system` (natural key includes source_system) — **recommended** so multi-source coexists |

Natural key **includes `source_system`** so SEC and firm_manual can coexist without overwrite.

### 7.4 Pipeline sketch (implementation later — not building now)

```text
1. Detect candidate filings (8-K earnings family, optional 10-Q/K)
2. Load bronze HTML (primary or EX-99.1)
3. Run guidance extractor → candidate facts + confidence + excerpt
4. Validate constraints (§5.3); quarantine rejects
5. Upsert silver sec_guidance_fact
6. Gold refresh → GUIDANCE_FACTS parquet / Snowflake export
7. dbt → EDGARTOOLS_GOLD.GUIDANCE_FACTS
```

Orchestration: attach to existing Branch B / fundamentals path or post-`earnings_release` parse hook (design choice for build).

### 7.5 Free-data note

No commercial vendor required for ERDP-02. SEC is free and preferred (see `assets/free-data-sources-erdp-01-04.md`).

---

## 8. Query patterns (agent / ER skills)

### 8.1 Latest guide for a CIK + metric + period

```sql
-- Conceptual; exact names per dbt
SELECT *
FROM EDGARTOOLS_GOLD.GUIDANCE_FACTS
WHERE cik = ?
  AND metric = 'revenue'
  AND fiscal_year = ?
  AND fiscal_quarter = ?   -- 0 for annual
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY cik, metric, fiscal_year, fiscal_quarter, is_non_gaap, source_system
  ORDER BY as_of DESC, ingested_at DESC
) = 1;
```

### 8.2 Guide in force before print date D

```sql
SELECT *
FROM EDGARTOOLS_GOLD.GUIDANCE_FACTS
WHERE cik = ?
  AND metric IN ('revenue', 'eps_diluted')
  AND as_of < ?              -- print / filing date
  AND fiscal_year = ?
  AND fiscal_quarter = ?
ORDER BY as_of DESC;
```

### 8.3 Join to earnings release

```sql
SELECT g.*, e.revenue_gaap, e.eps_gaap_diluted, e.filing_date
FROM EDGARTOOLS_GOLD.GUIDANCE_FACTS g
LEFT JOIN EDGARTOOLS_GOLD.EARNINGS_RELEASES e
  ON g.cik = e.cik AND g.accession_number = e.accession_number
WHERE g.accession_number IS NOT NULL;
```

### 8.4 Explore vs Agent-Grade

| Mode | Allowed? |
|------|----------|
| Explore / research SQL | Yes |
| Subject Bundle pure-SEC features | **No** (do not add guidance values to feature vector in phase-1) |
| Optional future Bundle section `latest_guidance` | Out of phase-1 product list; would need grade rules |

---

## 9. Acceptance criteria (normative)

Maps to REQUIREMENTS ERDP-02-* and sketch A02.*.

| ID | Criterion | Type |
|----|-----------|------|
| **A02.1** | For a curated sample of ≥5 accessions known to contain numeric revenue or EPS guidance, extractor produces ≥1 gold row each with ≥1 of low/mid/high non-null and `accession_number` set, `source_system` in (`sec_8k`,`sec_10q`,`sec_10k`). | Automated + fixture |
| **A02.2** | For those rows, join to `EARNINGS_RELEASES` or `FILING_DETAIL` on `(cik, accession_number)` succeeds when an ER/filing row exists. | Automated |
| **A02.3** | Documented recipe: given CIK + quarter + print date, select guide with `as_of < print_date` and matching period keys; compare to actuals from `EARNINGS_RELEASES` or `FINANCIAL_DERIVED`. | Doc + optional integration test |
| **A02.4** | Docs state Explore-only; CI/lint or review confirms no injection into pure-SEC feature keys. | Doc + review |
| **A02.5** (new) | Constraint: ≥1 value column non-null on 100% of published rows. | Automated |
| **A02.6** (new) | Coverage report: % of `EARNINGS_RELEASES` with `has_guidance=true` that have ≥1 `GUIDANCE_FACTS` row for same accession (target **best-effort**; initial goal ≥30% on liquid US sample, revisit). | Metrics job |
| **A02.7** (new) | `firm_manual` load: round-trip CSV → gold for 1 test CIK without SEC parse. | Automated |

---

## 10. REQUIREMENTS checklist (implementation backlog)

From milestone REQUIREMENTS (expanded):

- [ ] **ERDP-02-01** — Table exists in gold schema registry + Snowflake export + dbt gold model.  
- [ ] **ERDP-02-02** — A02.1 sample fixtures pass.  
- [ ] **ERDP-02-03** — A02.2 join tests pass.  
- [ ] **ERDP-02-04** — A02.3 documentation published (platform `docs/` or ERDP-05 extension).  
- [ ] **ERDP-02-05** — SEC preferred path + firm_manual path both documented and operable.  
- [ ] **ERDP-02-06** (recommended add) — A02.5–A02.7.  
- [ ] **ERDP-OPS** (if adopted) — Align with other gold fundamentals tables for path layout and manifests.

---

## 11. Quality, confidence, and failure modes

| Failure | Handling |
|---------|----------|
| Guidance table present but non-numeric | `has_guidance` may stay true; **no** GUIDANCE_FACTS row (or confidence=low quarantine) |
| Multiple currencies | Store `currency`; do not silently convert in phase-1 |
| Scale ($mm vs $) misread | Prefer edgartools scale detection patterns; confidence=low if ambiguous |
| Amended 8-K/A | New accession → new rows; do not delete prior accession rows |
| Conflicting guides same day | Multi-row by source_system or later as_of wins in “current” view |
| Parser regression | parser_version column; reprocess bronze without SEC re-fetch |

---

## 12. Privacy, compliance, labeling

- SEC data: public.  
- firm_manual: firm confidential — access control on warehouse roles (existing Snowflake RBAC patterns).  
- Forward-looking statements: product is **data**, not advice; ER skills remain responsible for disclaimers.  
- Explore products must not be advertised as Agent-Grade Decision Contract outputs.

---

## 13. Open design decisions (build kickoff)

| # | Decision | Default recommendation |
|---|----------|------------------------|
| D1 | Extract only from EX-99.1 vs full 8-K HTML | EX-99.1 first when identifiable; else primary |
| D2 | NLP vs table heuristics | Hybrid: table/outlook section heuristics first; NLP later |
| D3 | Midpoint auto-fill when only low/high | Optional view, not write-time required |
| D4 | Annual fiscal_quarter encoding | `0` |
| D5 | Whether to backfill history | Yes for bronze-available 8-K earnings cohort, best-effort |
| D6 | Quarantine table name | `sec_guidance_fact_reject` or dead-letter path |

---

## 14. Success metrics (product)

| Metric | Phase-1 target |
|--------|----------------|
| Fixture A02.1 pass rate | 100% on golden set |
| has_guidance → value extraction rate (A02.6) | Track; improve over time (initial ≥30% stretch) |
| firm_manual path | Works for ops pilot |
| Zero market fields in schema | Lint pass |
| ER skill docs can cite table | Doc complete |

---

## 15. Traceability

| Artifact | Path |
|----------|------|
| Milestone REQs | `.planning/workstreams/er-data-plane/REQUIREMENTS.md` |
| Parent spec | `.scratch/er-data-plane/spec.md` §3, §6 |
| Schema sketch | `.scratch/er-data-plane/assets/erdp-01-04-schema-sketches.md` |
| Free sources | `.scratch/er-data-plane/assets/free-data-sources-erdp-01-04.md` |
| Existing ER flag | `edgar_warehouse/parsers/earnings_release.py` (`has_guidance`) |
| Silver deferral note | `edgar_warehouse/silver_store.py` `sec_earnings_release` comments |
| Gold earnings schema | `edgar_warehouse/config/gold_schemas.yaml` `_FACT_EARNINGS_RELEASE_SCHEMA` |
| ADR pure-SEC | `docs/adr/0001-agent-decision-surface-first.md` |
| ER skill I/O | `.scratch/er-data-plane/assets/er-skills-io.md` |

---

## 16. Summary

**ERDP-02** turns “guidance exists” into **queryable numeric guidance facts** in **Gold Explore**, fed primarily by **SEC** filings already in the warehouse, with **firm_manual** as backup. It unblocks ER actuals-vs-guide workflows without violating pure-SEC Agent-Grade boundaries or requiring paid estimate vendors.

*Spec version: 1.0 — planning freeze companion; implementation not started.*
