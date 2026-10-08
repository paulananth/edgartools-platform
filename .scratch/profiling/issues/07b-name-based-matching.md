# 07b Name-based matching

Type: task. Phase: A. Blocked by: 03, 04. Map: [map](../map.md). Plan: [plan](../plan.md).

## Rulings (operator, 2026-10-06)

- "You are building a skill so fixed bar is useless name with class A is completely different from class C." A fixed engine-wide precision bar for name rules is dropped. The bar chosen earlier the same day ("99.5% and the 99% floor") is not built; the approved Mastering Policy (digest 1e38238f…03da4) and its two live name rules are unchanged.
- "Use name matching only when every thing else is not an option no id exists you just need to create a id using name." Ids and cross-reference ids come first; for records with none, an id is made from the name.
- "I am not checking anything": no labels or spot-checks by the operator.
- "You have to add the manufactured id to cross reference table": the id made from a name is a cross-reference, `name_id`, filled by the engine format `name_id@1` through the contract (no code), lookup only like every cross-reference (ticket 03).

## What this builds

The profiling skill learns from the data what an id made from a name must respect, and makes that id:
- **Distinguishing tokens:** names one token apart on records with different keys (share class A or C, series II or III, Inc or LLC) are kept as they are.
- **Variants:** names of one entity (its former or other names, or the same entity in two sources by a shared id) that differ by a token or two may be folded, but only when never seen apart.
- **Conflicts:** a pair seen both ways cannot be folded; the name alone cannot decide it.
- **Supporting attributes:** how often each agrees on pairs an id proves, and how often it separates near-homonyms.
- **The id:** `name_id@1`: the name's tokens, every one kept and none folded, hashed with sha256 behind the format name. Foldable variants are reported as evidence for a later format version, not applied (the trial shows folding gains nothing). The format is one entry in the engine's format table, the minimum the contract needs; "only where no id exists" is the skill's rule for which contracts map `name_id`, not something the format can check. Two sources with no shared id join on it only where it is held by exactly one record on each side; a name held twice joins nothing. On pairs an id does prove, the report counts where the name id agrees and where it contradicts.

## Checklist

- [x] GoF consult (matching.py, activation.py) 2026-10-06 17:45 ET
- [ ] ~~Fixed bar for every kind's name rules~~ dropped by the operator's ruling: "fixed bar is useless" (built, then reverted; policy unchanged) (added 2026-10-06 17:45 ET)
- [ ] ~~Below-the-bar steward queue in the engine~~ dropped: name matching is the last resort, made as an id; the engine is unchanged (built, then reverted) (added 2026-10-06 17:45 ET)
- [ ] ~~Operator labels and spot-checks 500 pairs per rule~~ dropped: "I am not checking anything" (added 2026-10-06 17:45 ET)
- [x] Evidence module `profiling/name_matching.py` and command `match_names.py`: distinguishing tokens, variants, conflicts, supporting attributes, homonym rate, the name id and its one-to-one join; personal names masked; DuckDB memory and spill capped; unit tests (`tests/unit/test_profiling_name_matching.py`, 129 profiling tests pass) 2026-10-06 18:52 ET
- [x] Trial on real data: every SEC filer (76,230) against the GLEIF records that can pair (12,834 of 3.4 million; the full set filled this machine's disk), SEC's own LEI as the proving id: 10,853 paired one to one, 223 of 226 LEI-checked pairs agree, the 3 others are SEC records stating another party's LEI; 130 LEI-proven pairs missed; figures on the subset are bounds ([RESULT](../trials/names/RESULT.md)) 2026-10-06 18:52 ET
- [x] Engine format `name_id@1` (NFKC, case fold, every token kept, sha256): the cross-reference table holds it through any contract; a test holds the profiling copy equal to the engine's, and a contract maps a name to it (`tests/mdm/test_clean_cross_reference.py`, `tests/unit/test_profiling_name_matching.py`) 2026-10-06 17:49 ET
- [x] SKILL.md (data-profiling): only when no id exists; the id goes to the cross-reference table, lookup only; REFERENCE.md (data-onboarding): the `name_id` row; guard clean, genericity lint passes 2026-10-06 17:49 ET
- [ ] ~~Add `name_id` to a live source contract~~ deferred to [07](07-readers-per-feed.md): all three live sources carry an id (CIK or LEI), so by the ruling none takes a name id; each new feed with no shared id gets it at onboarding (added 2026-10-06 17:49 ET; checked 2026-10-06 20:17 ET)
- [x] Review (Standards, Spec, GoF): GoF no findings; fixed from Standards and Spec: dropped tokens now tested as apart, fold count reported as a total, proved pairs the name id misses counted, `--personal` masks every name part, temp file removed on failure, file path bound as a parameter, sizes checked, ids trimmed alike, examples ordered, imports at module top, ticket text matches the id (3 new tests; trial rerun) 2026-10-06 18:57 ET
- [x] PR, CI, merge on word: #838, CI green (6 checks), merged on the operator's word as e4009a9c 2026-10-06 19:59 ET
- [x] J1, which function may bind a CIK to an LEI (handoff #860): the operator, 2026-10-08 06:19 ET: "Proven name rules may bind (Recommended)". A `name_census_match@1` rule (`sec-gleif-name-jurisdiction`, `sec-gleif-name-postal` in `rules/merge/kinds/company.yaml`) may bind when the name is unique on both sides and a second fact agrees, each rule switched on only with its measured proof and the operator's approval; anything less goes to a steward. The profiling `name_id@1` stays a lookup id in the cross-reference table and never binds. No change to either function. Codex records the same words on the Company merge-rule ticket (handoff J1) 2026-10-08 06:20 ET
