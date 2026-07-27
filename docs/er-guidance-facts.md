# ER guidance facts (ERDP-02)

**Status:** phase-1 Gold Explore product
**Preferred source:** SEC (`sec_8k` / `sec_10q` / `sec_10k`) — extracted from the
earnings-release guidance table
**Secondary source:** `firm_manual` (CSV/Parquet override or supplement)
**Grade:** **Explore only** — not pure-SEC Agent-Grade Decision Features
**ADR:** [0001-agent-decision-surface-first.md](./adr/0001-agent-decision-surface-first.md)
**Spec:** `.scratch/er-data-plane/specs/ERDP-02-guidance-facts.md`
**Code:** `edgar_warehouse.explore.guidance_facts`

Structured numeric guidance values (low/mid/high) linked to identity (CIK)
and, when SEC-sourced, to the originating accession — turning
`EARNINGS_RELEASES.has_guidance=true` ("guidance exists") into queryable
values.

---

## 1. Product

| Layer | Name |
|-------|------|
| Silver | `sec_guidance_fact` (+ `sec_guidance_fact_reject` quarantine) |
| Gold export / SOURCE | `GUIDANCE_FACTS` |
| dbt dynamic table | `EDGARTOOLS_GOLD.GUIDANCE_FACTS` |
| Python extractor | `extract_guidance_from_earnings_release` / `extract_guidance_from_table` |
| Python builder | `build_guidance_facts_table` |
| Gold SQL builder | `edgar_warehouse.serving.gold_models._build_fact_guidance` |

### Natural key

```text
(cik, metric, fiscal_year, fiscal_quarter, as_of, accession_number, is_non_gaap, source_system)
```

`source_system` is part of the key so an SEC-derived row and a `firm_manual`
row for the same period **coexist** rather than overwrite (ERDP-02-05).
`as_of` is also part of the key (unlike `EARNINGS_CALENDAR`'s collapsed base
key) so every guidance revision is retained — needed for A02.3's
guide-in-force-before-print recipe.

**Current view:** `is_current` in dbt = latest `as_of` (then `ingested_at`)
per `(cik, metric, fiscal_year, fiscal_quarter, accession_number,
is_non_gaap, source_system)`.

### Columns

`fact_key`, `cik`, `ticker`, `company_key`, `accession_number`, `metric`,
`period_type`, `fiscal_year`, `fiscal_quarter` (`0` = annual), `period_end`,
`value_low` / `value_mid` / `value_high`, `unit`, `currency`, `is_non_gaap`,
`as_of`, `source_system`, `source_ref`, `excerpt` (≤500 chars), `confidence`,
`parser_version`, `ingested_at`.

| `metric` (phase-1 minimum: `revenue`, `eps_diluted`) | |
|---|---|
| `revenue`, `eps_diluted` | Required — extractor must support these |
| `eps_basic`, `ebitda`, `ebit`, `net_income`, `gross_profit`, `operating_margin`, `free_cash_flow`, `capex` | Best-effort |
| `other` | Row detected but not classified — kept only via `firm_manual` (SEC extraction skips unclassified rows) |

| `period_type` | Meaning |
|---|---|
| `annual` | `fiscal_quarter = 0` |
| `quarterly` | `fiscal_quarter` 1-4 |
| `range_fy` | Multi-quarter range guidance |
| `other` | Anything else |

Constraint (A02.5, enforced at write time — see §4 quarantine): every row
has ≥1 of `value_low` / `value_mid` / `value_high` non-null; when both low
and high are set, `low <= mid <= high`.

**No price / mcap / PE columns** (ERDP-06 boundary) — see ADR 0001.

---

## 2. SEC extraction path (ERDP-02-A02.1/A02.2)

Extraction reuses bronze HTML already cached for `sec_earnings_release`
parsing — **no re-fetch**. `edgar_warehouse.parsers.earnings_release.
parse_earnings_release` calls `extract_guidance_from_earnings_release` when
`EarningsRelease.guidance` (an edgartools `FinancialTable`) is present, and
returns the candidates alongside the existing `sec_earnings_release` row:

```python
result = parse_earnings_release(accession_number, html_content, "8-K", cik, filing_date=filing_date)
result["sec_earnings_release"]        # existing: presence flags + GAAP metrics
result["sec_guidance_fact"]           # ERDP-02: accepted guidance rows
result["sec_guidance_fact_reject"]    # ERDP-02: rows that failed §5.3 constraints
```

### Row classification (D2: table heuristics first)

`map_metric(label)` classifies each guidance-table row label (e.g.
`"Revenue"`, `"Adjusted EBITDA"`, `"Non-GAAP Diluted EPS"`) into
`(metric, is_non_gaap)` via keyword matching — order-sensitive so
`"ebitda"` isn't misclassified as `"ebit"`. Unrecognized labels map to
`"other"` and are **not** kept from the SEC path in phase-1 (documented
limitation — NLP fallback is D2's phase-2 option).

### Value parsing

`parse_value_cell(raw)` handles a bare point value (`low = mid = high`), a
`"$X - $Y"` / `"X to Y"` range (`mid` = average), or an explicit
`(low, high)` tuple. Non-numeric cells (`"N/A"`, `"Not meaningful"`) yield
`(None, None, None)` and the row is dropped (not a reject — no candidate to
quarantine).

### Units

`EarningsRelease.guidance.scaled_dataframe` already multiplies AMOUNT rows
by the table's detected scale factor (thousands/millions/billions);
per-share/percentage rows are left unscaled. So post-extraction, `unit` is
inferred per metric: `per_share` for EPS metrics, `percent` for margin
metrics, `USD` otherwise — **not** the as-reported thousands/millions unit.

### Known limitation (phase-1)

When a guidance table gives the same metric across multiple period columns
in one row (e.g. both Q1 and FY guidance on one "Revenue" line), only the
**first non-empty cell** is extracted. Multi-period rows will need a
follow-up before this is complete for that shape.

---

## 3. `firm_manual` load path (ERDP-02-A02.7)

```csv
cik,metric,fiscal_year,fiscal_quarter,value_low,value_high,as_of
320193,revenue,2026,3,89000,93000,2026-07-15
320193,eps_diluted,2026,3,1.25,1.35,2026-07-15
```

```python
from edgar_warehouse.explore.guidance_facts import load_firm_manual_csv

rows = load_firm_manual_csv("pilot_guidance.csv")
# source_system defaults to "firm_manual", confidence defaults to "high",
# accession_number stays None (not required for firm_manual per §5.3).
```

`firm_manual` rows merge into the same silver `sec_guidance_fact` table as
SEC-extracted rows (`SilverDatabase.merge_guidance_facts`), coexisting via
`source_system` in the natural key — both flow through the same gold
builder (`_build_fact_guidance`) into one `GUIDANCE_FACTS` table.

---

## 4. Quarantine (D6)

Rows that fail `normalize_guidance_row`'s §5.3 constraints (no numeric
value, `low > high`, missing `as_of`, SEC source without
`accession_number`, invalid `fiscal_quarter`) are routed to
`sec_guidance_fact_reject` via `SilverDatabase.merge_guidance_fact_rejects`
instead of `sec_guidance_fact` — never silently dropped, never gold-published.
`validate_guidance_rows(rows)` returns `(accepted, rejected)` for callers
that need both.

---

## 5. Query patterns (agent / ER skills)

### 5.1 Latest guide for a CIK + metric + period

```sql
SELECT *
FROM EDGARTOOLS_GOLD.GUIDANCE_FACTS
WHERE cik = ? AND metric = 'revenue' AND fiscal_year = ? AND fiscal_quarter = ?
  AND is_current;
```

### 5.2 Guide in force before print date D (A02.3)

```sql
SELECT *
FROM EDGARTOOLS_GOLD.GUIDANCE_FACTS
WHERE cik = ?
  AND metric IN ('revenue', 'eps_diluted')
  AND as_of < ?              -- print / filing date
  AND fiscal_year = ? AND fiscal_quarter = ?
ORDER BY as_of DESC;
```

Compare the top row's `value_low`/`value_mid`/`value_high` to actuals from
`EARNINGS_RELEASES` (or `SEC_FINANCIAL_DERIVED`) for the same period.

### 5.3 Join to earnings release (A02.2)

```sql
SELECT g.*, e.revenue_gaap, e.eps_gaap_diluted, e.filing_date
FROM EDGARTOOLS_GOLD.GUIDANCE_FACTS g
LEFT JOIN EDGARTOOLS_GOLD.EARNINGS_RELEASES e
  ON g.cik = e.cik AND g.accession_number = e.accession_number
WHERE g.accession_number IS NOT NULL;
```

### 5.4 Explore vs Agent-Grade

| Mode | Allowed? |
|------|----------|
| Explore / research SQL | Yes |
| Subject Bundle pure-SEC features | **No** — do not add guidance values to the feature vector in phase-1 |

---

## 6. Acceptance

| ID | Criterion |
|----|-----------|
| **A02.1** | Curated sample of accessions with numeric guidance yields ≥1 gold row each with ≥1 of low/mid/high non-null and `accession_number` set — `tests/unit/test_guidance_facts.py::ExtractGuidanceFromTableTests` |
| **A02.2** | Rows with `accession_number` join to `EARNINGS_RELEASES`/`FILING_DETAIL` on `(cik, accession_number)` — §5.3 above |
| **A02.3** | Documented guide-in-force-before-print recipe — §5.2 above |
| **A02.4** | Explore-only labeling (this doc); no injection into pure-SEC feature keys |
| **A02.5** | ≥1 value column non-null on 100% of published rows — enforced in `normalize_guidance_row`, quarantined otherwise |
| **A02.6** | Coverage: % of `has_guidance=true` `EARNINGS_RELEASES` with ≥1 `GUIDANCE_FACTS` row for the same accession (best-effort, initial target ≥30%) — metrics job, not yet run against production |
| **A02.7** | `firm_manual` round-trip CSV → gold for ≥1 test CIK — `tests/unit/test_guidance_facts.py::FirmManualLoaderTests` |

---

## 7. Promotion checklist (Partial → Covered)

**Current coverage-matrix status: Partial, not Covered** (`.scratch/er-data-plane/coverage-matrix.md` F17). Full reasoning and source citations: `.scratch/erdp-coverage-promotion/issues/04-promotion-criteria-guidance-facts.md`.

**Blocking prerequisite — not yet done.** `has_guidance` (`edgar_warehouse/parsers/earnings_release.py:116-124`) and this product's own extractor (`guidance_facts.py:565-594`) both silently treat *any* exception during `.guidance` access/parsing as "no guidance issued." A real code bug is currently indistinguishable from a legitimate negative at the data layer — no acceptance query can tell them apart. Must be fixed (distinguish "confirmed absent" from "exception during access," e.g. log/count separately or route to `sec_guidance_fact_reject`) before promotion is evaluated at all.

Also note: Apple's one real production run reporting `rows_earnings_release: 0` does **not** establish that 8-K is an unreliable guidance source — that number reflects the earnings-release parser not matching any of the 30 parsed filings, a more basic signal than guidance extraction specifically coming up empty.

| # | Criterion |
|---|-----------|
| 0 | *(prerequisite above)* |
| 1 | `metric ∈ {revenue, eps_diluted}` supported at minimum, re-verified live |
| 2 | Every `has_guidance=false` `EARNINGS_RELEASES` row is a positive, exception-free determination (guaranteed once #0 lands) |
| 3 | **Extraction yield ≥ 90%** of `has_guidance=true` rows have ≥1 `GUIDANCE_FACTS` row for the same `accession_number`; the remainder must land in `sec_guidance_fact_reject` with a reason, not be silently dropped — this is the measured replacement for "is 8-K reliable," a stricter production bar than A02.6's exploratory ≥30% target above |
| 4 | Guide-vs-guide: for any CIK with guidance in two consecutive fiscal quarters, both quarters' rows exist |
| 5 | ≥1 of low/mid/high non-null on every published row (already enforced — re-verified live) |
| 6 | `source_system='sec_8k'` rows: `source_ref` matches `^sec_8k:[0-9]{10}-[0-9]{2}-[0-9]{6}:guidance:.+$` (the real format `guidance_facts.py:557` emits) and the embedded accession joins to a real `FILING_DETAIL`/`EARNINGS_RELEASES` row |
| 7 | `firm_manual` rows trace to a checked-in, git-reviewed CSV (no deterministic `source_ref` format to verify here — `guidance_facts.py:321-322`) |
| 8 | SEC-derived preferred; `firm_manual` overrides coexist by natural key (already enforced) |
| 9 | 100% join to `COMPANY`/`TICKER_REFERENCE`, identity-checked |
| 10 | Explore-only labeling re-affirmed |

**Not required for promotion:** universe-wide coverage — every consuming ER skill is per-request/single-company for this product, unlike consensus estimates.

**Residual risk:** the 90% yield bar is measured against *known* guidance tables (`has_guidance=true`); it cannot detect a systematic false-negative in `has_guidance` itself beyond what #0's exception count makes visible.

---

## 8. Deferred / out of phase-1 scope (spec §13)

- **D3** — Midpoint auto-fill when only low/high given: an optional
  read-side view, not computed at write time (`value_mid` stays `NULL`).
- **D5** — Historical backfill over the full bronze-available 8-K cohort:
  not run yet: extraction is wired into the standard per-filing fundamentals
  path (`fundamentals_ingest.py`), so it populates going forward and on any
  reprocessing pass, but a dedicated backfill pass hasn't been executed.
- **D2 (phase-2)** — NLP fallback for guidance given as prose rather than a
  detected table.
- Multi-period-column rows (see §2 known limitation).

---

## 9. Related

- Reactive actuals: `EDGARTOOLS_GOLD.EARNINGS_RELEASES` (`has_guidance` presence flag, GAAP metrics)
- [er-earnings-calendar.md](./er-earnings-calendar.md) — forward-looking dates (ERDP-03), separate product
- ERDP-01 consensus (when published) — estimates, distinct from company-issued guidance

---

*ERDP-02 implementation docs — 2026-07-26*
