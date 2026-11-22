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

## Checklist

- [ ] Decide, per column, its straight form: a child table keyed on the parent's key and an ordinal (a list of terms, inputs, links or
      assertions), or typed columns (a fixed set of flags or properties). Recommendation: child tables for `inputs`, `path` and
      `evidence`; one boolean column per flag of the line-item map for `flags`; typed columns for the properties a source rule declares
- [ ] The silver specs, the financials SQL (`financials/line_items.py`, `measures.py`), the relationship builder and the answer keys follow
- [ ] The company-facts cohort proof gives the same figures after the change
- [ ] Learning → skill: the silver-table rule (no JSON column) in the owning skill, or "none"
