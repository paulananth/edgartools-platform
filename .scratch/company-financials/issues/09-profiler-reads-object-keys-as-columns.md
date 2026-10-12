# 09 Profiler gap: objects keyed by data are read as columns

Type: task. Status: open. Blocked by: none. Map: [map](../map.md).

## Question

The data-profiling skill reads a JSON object's keys as columns, so a document keyed by data (company facts: one key per concept, 633 in one filer) becomes thousands of columns. Generic fix in the skill (Claude's path): when an object's keys are many and its values share one shape, read it as a list with its key as a column. Until then `capture/to_facts_parquet.py` writes the long form. Its own branch, tests, three-axis review.
