# 18: Silver holds straight columns, not JSON

Status: resolved
Type: grilling

Operator, 2026-11-22, while ticket 17 changed the silver writer: "you should not be using json just straignt data so easy access is
possible". The writer sends plain typed columns. Six silver columns, though, store a JSON document a reader must unpack:

| Table | Column | Holds |
|---|---|---|
| `company_line_item` | `inputs` | for a computed figure, each term's concept (or line item), accession number and value |
| `company_line_item` | `flags` | the words a reader must know (computed, includes NCI, cover-page date, kind, ...) |
| `company_measure` | `inputs` | each line item the measure read, with its year, value, concept and accession number |
| `relationship` | `path` | the chain of links a calculated link walked |
| `relationship` | `properties` | the dated details the source rule keeps with the period |
| `relationship` | `evidence` | the assertion id of each stored record that states the link |

## Findings (data-profiling and data-modeling, 2026-11-22 19:24 ET)

Read from the builders and the rules, since no store holds these tables today (counts, no values):

- `company_line_item.flags`: a row carries at most one wording flag (a map entry has one `flag` or one `kind`; a computed entry adds
  "computed"; the revenue check adds one more). The map has 12 wording flags (two are one idea spelled amortisation and amortization),
  3 industry kinds (bank, insurer, utility) and 1 quality flag. Eleven boolean columns could never be true together, so the straight
  form is `computed` BOOLEAN, `basis` VARCHAR (the one wording), `industry_kind` VARCHAR, `revenue_quality_check` BOOLEAN. The
  wording-to-match-type table the line-item map already holds (broad, narrow, close) stays the map's.
- `company_line_item.inputs`: filled for 14 computed entries (at most 3 terms each) and for the cover-page figure (1 input, with its
  date). A list, so a child table `company_line_item_input`: key (company_key, line_item, fiscal_year, position); columns concept,
  line_item_ref (a term can be another line item, then no filing), accession_number, value DECIMAL(38,10), as_of DATE.
- `company_measure.inputs`: a set of named inputs per measure (top and bottom, return and balance and prior balance, start and end,
  operating cash flow and capex, and the tax rate with its source). Child table `company_measure_input`: key (company_key, measure,
  fiscal_year, window_years, role); columns input_fiscal_year, value, concept, accession_number. The tax rate is a part whose value is
  the rate (to 10 places) and whose `basis` holds its source.
- `relationship.evidence`: a list per link, repeated on each period row today. Child table `relationship_evidence`: key
  (relationship_id, assertion_id), one row per link, no repeat.
- `relationship.path`: a list per derived period. Child table `relationship_path`: key (relationship_id, valid_from, position).
- `relationship.properties`: the names a source rule declares (7 today, text or boolean). Typed nullable columns named as the
  source rule names them; one table-wide column set grows only with a rule.
- Silver keeps no copy of a master field: none of these columns is one.
- A column leaves a store by a new table, never by a drop (data-modeling, ticket 143): the writer adds columns and refuses a changed spec.

## Checklist

Operator, 2026-11-22: "consult data profiling and modeling skills first", then "design from scratch and finalize tables delete old
tables update all dependencies". The forms below are the findings above; the tables keep their names (no store is live; the owner drops
an old table and its registry row, init runbook step 6).

- [x] Consult data-profiling and data-modeling: shapes measured from the builders and rules, forms decided per column (2026-11-22 20:31 ET, findings above)
- [x] Decide each column's straight form: `flags` → `computed`, `basis`, `industry_kind`, `revenue_quality_check` (a row carries at most one wording, so no boolean per flag); `inputs` → `company_line_item_input` and `company_measure_input`; `path` → `relationship_path`; `evidence` → `relationship_evidence`; `properties` → seven typed columns on `relationship` (2026-11-22 20:31 ET)
- [x] The silver specs, the builders, the derive worker and the target steps follow: `company_line_item`, `company_measure`, `relationship` and the four new tables; each input table is its own derive step over the same query (2026-11-22 20:31 ET; `tests/integration/test_company_line_item_silver.py`, `test_company_measure_silver.py`, `test_silver_derive_worker_postgres.py`, `tests/unit/test_straight_columns.py`)
- [x] A snapshot of a list its parent may not own is not refused: `may_be_empty` (2026-11-22 20:31 ET; `test_a_snapshot_that_may_be_empty_is_emptied_by_an_empty_delivery_and_any_other_refuses_it` failed first with "A silver table spec holds [...]", the unknown key)
- [x] Every dependent follows: mirror list, data-sharing list, catalog, mapping document, recorded target steps, runbook, `deploy-silver.sh` (globs the specs) (2026-11-22 20:31 ET; unit suite 1,867 passed)
- [x] A traced figure is rounded to the column's 10 places: the cohort build refused a computed return and a tax rate of more than 10 decimals (2026-11-22 20:31 ET; `test_a_tax_rate_that_does_not_end_is_stored_to_ten_places` failed with "A figure does not fit DECIMAL(38,10) exactly")
- [x] The company-facts cohort proof gives the same figures: 96,807 line items, 168,360 measures, every figure, flag, input and measure equal to the old tables (6,589 line-item inputs, 404,611 measure inputs, 0 differences; builds 41 s, 29 s, 20 s, 50 s) (2026-11-22 20:31 ET)
- [x] The answer key follows: no answer-key file of this repository reads `inputs` or `flags` (searched), and every measure value equals the old table's (2026-11-22 20:31 ET)
- [x] Review (Standards, Spec, GoF, Haiku): fixed a `rows_of` caller list in two test files, a stored period's properties (null and flag round trip, so the engine keeps a start), input positions by term number, a child read of a removed period, `may_be_empty` on every child list, `source_start_date_is_provisional` as BOOLEAN, spec-refusal tests, the GOLD list. Left: two `straight()` and `build()` copies (two callers, no pattern), a manual owner drop in the runbook (a destructive drop stays the owner's explicit act) (2026-11-22 20:31 ET)
- [x] Learning → skill: data-modeling ("No silver column holds JSON", `may_be_empty`) and company-financials (five tables) (2026-11-22 20:31 ET)
