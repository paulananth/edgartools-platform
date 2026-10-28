# 11 The silver table spec for financial line items

Priority: 43, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/11-silver-table-spec-for-financials.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: grilling. Status: resolved (2026-10-22 09:18 ET, operator: "Approve the spec (Recommended)"). Blocked by: 35, 38 (both resolved); also built on 37, 39, 40, 42 and 128. Map: [map](../../company-financials/map.md).

## Question

Write the silver table spec (profiling's spec format, `docs/specs/profiling/findings.md` silver section): grain (company, line item, period start, end, as at?), keys, columns (value, unit, chosen concept, accession, filed date, frame, flags such as "includes NCI"), the link to the MDM Company (by CIK, with overlap %), as-of and as-at columns per ticket 03, load mode, and where the raw facts table sits beside it.

## Checklist

- [x] Review of the financials tickets (35, 37–48, 128) for gaps before the spec ("Design review", below) (2026-10-22 08:14 ET)
- [x] Spec drafted in the profiling silver format (`docs/specs/profiling/findings.md` section 6) from the rulings of 35, 38, 39, 40, 42 and 128 (2026-10-22 08:14 ET)
- [x] Follow-on fixes to tickets 44, 45 and 46 from the review (2026-10-22 08:14 ET)
- [x] Operator's approval of the spec (operator: "Approve the spec (Recommended)") (2026-10-22 09:18 ET)
- [x] Learning → skill (operator: "Add this to the correct skill - review"): the general practice in `skills/data-modeling/SKILL.md` Hard stops (review every related ticket before a spec or a build); the financials findings in `skills/company-financials/SKILL.md`, "Silver tables and their review" (2026-10-22 08:14 ET)

## Design review (2026-10-22)

The operator asked for `/design-review` first. That skill audits a live web page; the financials have none, so the review read the decision and build tickets for gaps instead. Findings, each with what it changes:

1. **Ticket 43 waited only on 35 and 38**, but its columns also come from 39 (measures), 40 (the reader's shape), 42 (currency, IFRS, format) and 128 (exact numbers). The spec below uses all six.
2. **Ticket 45 still offered "a custom step"**; ticket 40 ruled configured reading only, with `big_numbers: text` on `units` (ticket 128). Updated.
3. **Ticket 46 named only the us-gaap rules**; ticket 42 adds the `ifrs-full` lists, the kind flags and the statement format from the SIC code. Updated.
4. **Ticket 44's answer key** lacked the hard cases tickets 42 and 35 added: an IFRS filer, a financial-services filer (its "not meaningful" nulls), mixed currencies and a changed fiscal year end. Updated.
5. **The MDM Company is empty locally** (ticket 37: 0 of 329 CIKs match a master). The link keeps the CIK and an empty MDM id until Company is mastered, as the silver spec says; the statement format, read from the Company's SIC code, is "unknown" until then (below).
6. **Old numbering.** Several tickets still say "ticket 03/06/07/10/11/12" in the old effort's numbers (35, 38, 39, 42, 43, 44 here). Left as is; each ticket's header says so.

## The spec (approved)

Corrected (2026-10-28 16:55 ET, ticket 46; operator, 2026-10-28: "Engine step, local (Recommended)"): `company_line_item` and the facts' flattening are built by a configured engine step and land through the silver writer, not by dbt; the line items are 23 codes of RDM's `financial-line-items`. `company_fact`'s key reads `period` (start/end, or an instant's date) in place of `period_start` and `period_end`, since the silver writer refuses an empty key column; the filer is `company_key` (the 10-digit CIK the Company's Dataset Contract keys by) in place of `cik`, one system of record (operator, 2026-10-28: "silver must not have duplicate fields"). The figure check is the writer's own: it refuses a figure a DECIMAL column cannot hold exactly.

Three silver tables. The facts land from the reader (ticket 40) and dbt flattens units and facts; the line items and the measures are built from the facts by dbt, rebuilt whole each run. Rules configuration (the line-item map and the measure definitions) sits under `rules/`, with its version on every row it produced.

### 1. `company_fact`: every filed fact

```yaml
table: company_fact
grain: one row per filed fact (company, taxonomy, concept, unit, period, filing)
columns:
  - {name: cik, type: bigint, nullable: false, definition: the filer's SEC id, source: document cik}
  - {name: taxonomy, type: text, nullable: false, definition: the taxonomy the concept is from (us-gaap, ifrs-full, dei, ...), source: concepts table name}
  - {name: concept, type: text, nullable: false, definition: the reported concept, source: entries key}
  - {name: unit, type: text, nullable: false, definition: the unit as filed (USD, shares, USD/shares, pure, ...), source: units key}
  - {name: currency, type: text, nullable: true, definition: ISO 4217 code when the unit is a currency or a currency per share, else empty, source: from unit}
  - {name: period_start, type: date, nullable: true, definition: start of a duration; empty for an instant, source: start}
  - {name: period_end, type: date, nullable: false, definition: end of the period (the instant's date), source: end}
  - {name: value, type: "decimal(38,10)", nullable: false, definition: the figure as filed, never rounded, source: val (big_numbers text)}
  - {name: accession, type: text, nullable: false, definition: the filing that reported it, source: accn}
  - {name: filed, type: date, nullable: false, definition: the filing date, source: filed}
  - {name: form, type: text, nullable: false, definition: the form filed (10-K, 10-Q, 20-F, ...), source: form}
  - {name: fiscal_year_filed, type: bigint, nullable: true, definition: the filing's own fy label; kept, never a key, source: fy}
  - {name: fiscal_period_filed, type: text, nullable: true, definition: the filing's own fp label (FY, Q1, ...); kept, never a key, source: fp}
  - {name: frame, type: text, nullable: true, definition: the SEC calendar frame, a cross-check only, source: frame}
key: [cik, taxonomy, concept, unit, period_start, period_end, accession, filed]
links:
  - {columns: [cik], kind: company, source_code: sec.submissions.company, to_part: company, source_key: cik, mdm_id_column: company_mdm_id, inclusion: 1.0}
time: {as_of: period_end, as_at: filed, event_time: null}
partition: [cik]
load_mode: append
checks:
  - {id: exact_value, check: in_set, column: value_fits, values: [true], on_fail: flag, why: a value that does not fit decimal(38,10) exactly is flagged, never rounded}
why: >
  Keep every filed copy (ticket 35). The key is the measured eight-column key
  (ticket 37: 0 duplicates over 5,134,979 facts). Append, since a filed fact
  never changes; a restatement is a new filing. fy and fp are kept as filed but
  never key a year (ticket 35). Value is exact (ticket 128): the largest filed
  integer has 20 digits, within decimal(38,10). Inclusion 1.0 is against the
  captured Company list; the local MDM has no Company yet (ticket 37).
```

### 2. `company_line_item`: the 19 standard line items

```yaml
table: company_line_item
grain: one row per company, line item, period and filing (every filed copy)
columns:
  - {name: cik, type: bigint, nullable: false}
  - {name: line_item, type: text, nullable: false, definition: one of the 19 standard line items (ticket 38)}
  - {name: period_start, type: date, nullable: true}
  - {name: period_end, type: date, nullable: false}
  - {name: period_kind, type: text, nullable: false, definition: "annual (364-371 days), quarter, instant or transition"}
  - {name: fiscal_year, type: bigint, nullable: true, definition: "Compustat FYEAR of period_end for an annual period: an end in January to May is the previous year (ticket 35, operator 2026-10-22); the later year end wins a year"}
  - {name: value, type: "decimal(38,10)", nullable: true, definition: empty when no concept was filed}
  - {name: unit, type: text, nullable: true}
  - {name: currency, type: text, nullable: true, definition: ISO code; the figure stays in its reporting currency (ticket 42)}
  - {name: taxonomy, type: text, nullable: true, definition: us-gaap or ifrs-full, the one the filer files in (ticket 42)}
  - {name: concept, type: text, nullable: true, definition: the concept chosen by the ordered list, or "computed"}
  - {name: inputs, type: json, nullable: true, definition: for a computed value, the concepts and accessions it was built from}
  - {name: accession, type: text, nullable: true}
  - {name: filed, type: date, nullable: true}
  - {name: is_latest, type: boolean, nullable: false, definition: the latest-filed copy for this company, line item and period; the default (ticket 35)}
  - {name: flags, type: "text[]", nullable: false, definition: "computed, includes NCI, continuing operations, cover-page date, revenue quality check, industry kind (bank, insurer, REIT, utility)"}
  - {name: null_reason, type: text, nullable: true, definition: "no concept filed" when value is empty}
  - {name: statement_format, type: text, nullable: false, definition: "industrial, financial services or unknown, from the Company's SIC code (ticket 42)"}
  - {name: rule_version, type: text, nullable: false, definition: the named version of the line-item map that chose the value}
key: [cik, line_item, period_start, period_end, accession]
links:
  - {columns: [cik], kind: company, source_code: sec.submissions.company, to_part: company, source_key: cik, mdm_id_column: company_mdm_id, inclusion: 1.0}
time: {as_of: period_end, as_at: filed, event_time: null}
partition: [cik]
load_mode: snapshot
why: >
  Built by dbt from company_fact and the rules map, rebuilt whole each run
  (snapshot), so a new filing moves is_latest without editing rows. Every filed
  copy keeps a row (ticket 35). A missing item is a row with an empty value and
  its reason, so it is counted (ticket 38). The format comes from the Company
  master's SIC code; until Company is mastered it is "unknown".
```

### 3. `company_measure`: the stored measures

```yaml
table: company_measure
grain: one row per company, measure, fiscal year and window
columns:
  - {name: cik, type: bigint, nullable: false}
  - {name: measure, type: text, nullable: false, definition: "e.g. revenue CAGR, ROE (average balance), ROE (beginning balance), gross margin"}
  - {name: fiscal_year, type: bigint, nullable: false, definition: the window's last year}
  - {name: window_years, type: bigint, nullable: false, definition: "1 for a single-year measure; 1, 3, 5 or 10 for a CAGR"}
  - {name: value, type: "decimal(38,10)", nullable: true, definition: raw, no truncation or smoothing (ticket 39)}
  - {name: currency, type: text, nullable: true, definition: the inputs' one currency, empty for a ratio of like amounts}
  - {name: null_reason, type: text, nullable: true, definition: "not meaningful, missing year, fiscal year changed, mixed currencies, not meaningful for financial services, denominator zero or negative"}
  - {name: inputs, type: json, nullable: false, definition: the line-item values, concepts and accessions used}
  - {name: definition_version, type: text, nullable: false}
key: [cik, measure, fiscal_year, window_years]
links:
  - {columns: [cik], kind: company, source_code: sec.submissions.company, to_part: company, source_key: cik, mdm_id_column: company_mdm_id, inclusion: 1.0}
time: {as_of: fiscal_year, as_at: null, event_time: null}
load_mode: snapshot
why: >
  Stored, built from silver (ticket 39), from the latest-filed line items;
  rebuilt whole each run. Each row names its inputs and definition version,
  so a value can be traced to its facts and filings (ticket 48).
```

`as_at: null` on the measure: a measure is rebuilt from the latest copies, so its as-at is the run, kept by the writer's `loaded_at`.
