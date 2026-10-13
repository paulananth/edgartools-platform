# Fundamentals acquisition requirements from valuation workbook

Status: in progress (requirements extraction only). Owner: Codex on
`codex/fundamentals-workbook-requirements-20261013`; starting main `8f90cb9c`.

Request: read `/Users/aneenaananth/Downloads/Financial-Model-and-Valuation-Template.xlsx`
and create the list of data needed for fundamentals acquisition.

The source workbook stays unchanged. This task creates a traceable requirements
catalog; it does not resume parked financials implementation, fetch SEC data,
select investment assumptions, approve rules or activate a pipeline. Preserve
Claude's Company financials map and active L7 paths.

## Parts

- [x] Inspect all seven worksheets, cell/formula dependencies, defined names, comments, drawing text and relevant embedded instructions; record source hash. — 2026-10-13 07:42 ET; ZIP/XML inspection including shared formulas, comments/drawings; original SHA verified.
- [x] Separate acquired reported facts, market inputs, analyst assumptions, computed outputs and supporting metadata. — 2026-10-13 07:42 ET; 115-entry category audit; JSON/CSV/Excel equality verified.
- [x] Specify each field's definition, fiscal period/units, source route and workbook references; include note-driven requirements and reconciliation additions explicitly. — 2026-10-13 07:42 ET; 243 cell/region references resolve; 102 financial rows and 30 valuation cells covered.
- [x] Identify model/data ambiguities affecting acquisition: shares, periods, currency/scale, cash flows, forecasts, missing data and source coverage. — 2026-10-13 07:42 ET; 14 GAPS entries match Excel; source formula checks verified.
- [x] Deliver readable Markdown, machine-readable CSV and a separate Excel requirements workbook. — 2026-10-13 07:42 ET; 115 JSON/CSV/Excel records match; Markdown IDs and output hashes verified.
- [ ] Create the requested PR and hand over the catalog, unresolved choices and boundaries to Claude.
- [ ] Verify coverage against source rows/formulas, output consistency, source immutability and ownership guard; commit the requirements artifacts.

## Completion

Each substantive financial row and non-financial input must be represented as an
acquisition requirement, assumption or derivation with a source reference. Added
controls/reconciliation fields must be distinguishable from literal template
inputs. Source routes and taxonomy mappings are candidates, not qualified
capabilities. No claim of production acquisition completion follows this list.
