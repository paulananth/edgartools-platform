# Profiling names the data quality rules, the RDM code sets and every silver field, and the catalog shows them

Priority: 87, tier 1, in flight (raised by the operator, 2026-10-15). Map: [Rebuild priorities](../map.md).

Type: task (skills and the catalog). Status: claimed (Claude, 2026-10-15 ET, branch `claude/profile-to-catalog`). Blocked by: none.

## Why

Operator, 2026-10-15, onboarding N-PORT (ticket 79): "any need to go to rdm ? please not this data-onboarding skill first do mdm, 2) as part of profililing, need to identify both data quality rules and rdm and all silver fields and document in the data catalogue please update the skill and test it".

What profiling wrote before this ticket:
- **Data quality:** defects found (`quality`), not the rules a part needs when it has no defect: a part with clean data got no checks.
- **RDM:** each part's `code_lists`, with a proposed code set name, but no list of the code sets the data set needs.
- **Silver:** a table spec only for parts MDM does not own; a master part's fields had no silver spec.
- **Catalog:** published one way from the rules files (operator, 2026-09-28), so nothing profiling found reached it until a Dataset Contract mapped it.

And data-onboarding's plan-parts ordered reference parts (RDM) first.

## What changes

1. **Onboarding order:** master parts (MDM) first, with their "together" relationships; then reference parts (RDM code sets); then silver (transaction parts and "separate" relationships). RDM is needed only where a value's meaning comes from a code set.
2. **Profiling proposes, for every part:**
   - every data quality rule the part needs on every load, in `quality` with the rows that fail it: above 0 a defect, 0 a rule the clean data passes (a record key column filled; an identifier's one shape and its check digit; a link that resolves; a code list), each with a proposed `on_fail`.
   - `code_sets` (top level): one entry per proposed RDM code set, naming the columns that use it, how many codes, and an existing code set when one matches.
   - `silver` for every part, masters included: every column a silver field with type, nullability and sensitivity; a master part's spec carries its MDM id column.
3. **The catalog:** onboarding writes the approved profile's names and counts (never a value from the data: the repository is public) to `rules/sources/<source>/profile.yaml`; `rules catalog plan` adds a `silver` database (a table per part, a column per field, with its quality rules) and an `rdm` database (a table per code set), with lineage from each part to the code sets it uses.

## Checklist

- [x] GoF consult: leave the shapes; detectors stay plain functions (a rule is a detector's item with 0 failing rows); `catalog.plan` gains a `_profile` helper beside `_dataset`; the code-set naming and the silver spec each live in one function both the run and the summary call 2026-10-15 06:54 ET
- [x] data-onboarding plan-parts: MDM first, then RDM, then silver (data-onboarding and data-profiling; data-platform states no order) 2026-10-15 06:54 ET
- [x] Profiling: every rule in `quality` with its failing rows (0 for a rule the clean data passes; a stand-in no longer counts as another shape), `code_sets` top level, `silver` for every part (a master's rows carry their own `mdm_id`); spec `docs/specs/profiling/findings.md`; tests in `test_profiling_run.py` and `test_profiling_quality.py` 2026-10-15 06:54 ET
- [x] `profile_data.py catalog` writes `profile.yaml` (names and counts only) from approved findings, refusing a draft; a test finds no sample, example or code from the data in it 2026-10-15 06:54 ET
- [x] Catalog: `silver` and `rdm` databases and their lineage from `profile.yaml`; tests in `test_rules_catalog.py` 2026-10-15 06:54 ET
- [x] Skills: data-profiling, data-quality, data-onboarding name the new outputs; genericity lint passes 2026-10-15 06:54 ET
- [x] Tried on the approved 13F and N-PORT findings (made before this ticket; the summary rebuilds code sets and silver specs from their parts): 48 silver tables, 359 fields (159 with a data quality rule, 116 with a code set), 112 RDM code sets (the N-PORT findings name all 112, since they profiled the 13F tables too; the 13F findings 4 of them; most code lists have no proposed name, so each is named for its column), 123 lineage links; of 6,080 sample values, none in either summary (the 18 word matches are inside column and part names). A re-profile adds the clean-data rules, which these older findings lack 2026-10-15 06:54 ET
- [ ] Three-axis review; PR, CI green, merge on the operator's word
- [ ] Learning → skill
