# Configured parsing: build the engine, or keep per-source readers

Type: grilling (HITL)
Status: open
Blocked by: Codex's custom-parsing research (`codex/custom-parsing-research-20261002`, `docs/research/custom-parsing-inventory-2026-10-02.md`)

## Question

Sources are still read by per-source Python: `company_source.py`, `gleif_source.py`, and the Person fixture conversion. The configured engine is not built:
- readers for json, jsonl, xml, csv and zip;
- primitives;
- `custom.py`;
- run a source into MDM;
- the profiler.

That is rules skill tickets 03, 04 and 06. Forms 3/4/5 and the later Person feeds need parsers, and the ownership parser was deleted in slice 2a.

Decide:
- whether to build the engine before the Forms 3/4/5 feed or after;
- its smallest first slice;
- whether the existing Company and GLEIF readers move onto it (rules skill 10).
