# 09 Profiler gap: objects keyed by data are read as columns

Priority: 41, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/09-profiler-reads-object-keys-as-columns.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task. Status: open. Blocked by: none. Map: [map](../../company-financials/map.md).

## Question

The data-profiling skill reads a JSON object's keys as columns, so a document keyed by data (company facts: one key per concept, 633 in one filer) becomes thousands of columns. Generic fix in the skill (Claude's path): when an object's keys are many and its values share one shape, read it as a list with its key as a column. Until then `capture/to_facts_parquet.py` writes the long form. Its own branch, tests, three-axis review.
