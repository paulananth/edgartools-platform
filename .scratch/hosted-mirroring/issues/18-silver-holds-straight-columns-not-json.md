# 18: Silver holds straight columns, not JSON

Status: open
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
  fiscal_year, window_years, role); columns input_fiscal_year, value, concept, accession_number. The tax rate is a role whose value is
  the rate and whose concept holds its source.
- `relationship.evidence`: a list per link, repeated on each period row today. Child table `relationship_evidence`: key
  (relationship_id, assertion_id), one row per link, no repeat.
- `relationship.path`: a list per derived period. Child table `relationship_path`: key (relationship_id, valid_from, position).
- `relationship.properties`: the names a source rule declares (7 today, text or boolean). Typed nullable columns named as the
  source rule names them; one table-wide column set grows only with a rule.
- Silver keeps no copy of a master field: none of these columns is one.
- A column leaves a store by a new table, never by a drop (data-modeling, ticket 143): the writer adds columns and refuses a changed spec.

## Checklist

- [ ] Decide, per column, its straight form: a child table keyed on the parent's key and an ordinal (a list of terms, inputs, links or
      assertions), or typed columns (a fixed set of flags or properties). Recommendation: child tables for `inputs`, `path` and
      `evidence`; one boolean column per flag of the line-item map for `flags`; typed columns for the properties a source rule declares
- [ ] The silver specs, the financials SQL (`financials/line_items.py`, `measures.py`), the relationship builder and the answer keys follow
- [ ] The company-facts cohort proof gives the same figures after the change
- [ ] Learning → skill: the silver-table rule (no JSON column) in the owning skill, or "none"
