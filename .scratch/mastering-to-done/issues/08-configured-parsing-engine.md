# Configured parsing: build the engine, or keep per-source readers

Type: grilling (HITL)
Status: resolved
Blocked by: none (Codex's research merged in #784: `docs/research/configuration-replacement-results-2026-10-02.md`)

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

## Answer

The operator, 2026-10-02:
- "build the engine first, custom parcers are allowed for complicated lookups and transfromations but they are the last resort" (by 11:24 ET);
- "rust engine, for calls to edgartools keep python rust engine is under the cover always using python" (by 11:24 ET).

1. **The configured engine is built before the Forms 3/4/5 feed.** Every source is then read through it: the rules files describe the reading, the checks and the mapping.
2. **The engine is Rust, behind a Python interface.** It grows from Codex's prototype `crates/source-contract`. Python calls it: Bookkeeping, the rules commands and Clean MDM never call Rust directly. Calls to edgartools stay in Python.
3. **A custom parser is the last resort**, only for a lookup or transformation the configuration can't state. It is a named Python step that the rules file declares, with its own tests, and each one is listed in the source's Mapping Document.
4. **Acceptance:** the engine must close the counterexamples in Codex's research (`docs/research/configuration-replacement-results-2026-10-02.md`) before a source moves onto it:
   - keep valid CDATA;
   - reject malformed XML, a wrong root, namespace, header or record count, and a DTD;
   - read JSON;
   - run declared custom steps;
   - express GLEIF's scope, deletion, single-period and date-order gates.

   Codex's 41 Python and 13 Rust research tests become its acceptance suite.

**New tickets:**
- 15: Rust engine core behind Python;
- 16: GLEIF on the engine;
- 17: SEC Company on the engine.

Tickets 09 (test, check and Preview) and 10 (Forms 3/4/5) now build on ticket 15.
