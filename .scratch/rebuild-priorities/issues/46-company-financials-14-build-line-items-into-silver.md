# 14 Build: standard line items into silver

Priority: 46, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/14-build-line-items-into-silver.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task. Status: open. Blocked by: 38, 42, 43, 45. Map: [map](../../company-financials/map.md).

## Question

Implement the line-item selection (ticket 38's rules; ticket 42's reporting currency, `ifrs-full` lists, kind flags and statement format from the SIC code) and land the silver table of ticket 11 through the silver writer (profiling ticket 06), with each value's chosen concept and accession. Acceptance: none of the research note's nine hazards (section 5) is possible; the answer key's line items match.

## RDM: the line items as a code set (operator, 2026-10-22)

"Yes, code set + crosswalk (Recommended)", asked "Do you need ifrc or gaap labels in
rdm": the 19 standard line items are an RDM code set (`financial-line-items`: code,
label, definition, kind), crosswalked to the `us-gaap` and `ifrs-full` concepts each
uses (outside standards, `to_version: outside`). The rules YAML names those RDM codes
and holds only the try-order and the computed fallbacks, which a crosswalk cannot
express. The taxonomies themselves are not loaded into RDM: each fact keeps its
concept's label and description in silver.

- [ ] The RDM code set `financial-line-items` drafted, its crosswalk to research 01
  and 04's concepts, approved in the operator's words and published
- [ ] The rules YAML names the RDM codes; a test holds every concept in its lists
  equal to the code set's crosswalk
