# 13 Build: the company facts reader

Priority: 45, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/13-build-company-facts-reader.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task. Status: open. Blocked by: 40, 41, 128, 134. Map: [map](../../company-financials/map.md).

## Question

Implement the reading ticket 40 decided: a configured source-extract contract under `rules/sources/` (no custom step), one table per taxonomy with `big_numbers: text` on `units` (ticket 128), starting from `.scratch/company-financials/research/03-company-facts-trial-contract.yaml`, with its tests on captured files; GoF consult before code; three-axis review; merge on the operator's word.

## Checklist

- [x] GoF consult: not needed, configuration only (a rules YAML and its tests; no code file) (2026-10-22 18:08 ET)
- [x] Contract `rules/sources/sec.company-facts/facts.yaml` from the trial (research 03): nine taxonomy tables, the `taxonomies` table refusing an unknown one, each concept row with the filer's CIK, its label and description, its `units` whole (2026-10-22 18:08 ET)
- [x] Finding: the filer's CIK is a JSON number in 262 captured files and digit text in 105 (103 ten-digit, 2 seven-digit); one file is an empty object. `integer` reads both forms as one bigint; the empty file lands nothing (2026-10-22 18:08 ET)
- [x] Finding: every decimal figure reached Python as a float (323,634 figures; none loses a digit today). Operator, 2026-10-22: "For financial projects never use integer's use only bigint or big decimal", "Big decimal": engine ticket [134](134-exact-decimals-in-configured-reading.md) adds `decimals: text`, declared on `units` (2026-10-22 18:08 ET)
- [x] Ticket 43's spec corrected under that ruling: four `integer` columns now `bigint`; the fiscal year column says Compustat FYEAR (2026-10-22 18:08 ET)
- [x] All 368 captured files read: 5,134,979 facts and 139,643 concepts, every file equal fact by fact to the file read directly in exact decimals, every row's CIK equal to its file's, no float (`.scratch/company-financials/reader/full_read.py`, 123 s, on ticket 134's engine) (2026-10-22 18:08 ET)
- [x] Tests on invented documents, `tests/engine/test_company_facts_reading.py`: one table per taxonomy, CIK as number and padded text, every figure exact, an unknown taxonomy refuses, an empty document and a concept with no facts; 7 pass on ticket 134's engine (2026-10-22 18:08 ET)
- [x] Rebased onto main after #1139 merged; 46 tests of the areas it touches pass on main's engine (2026-10-22 18:17 ET)
- [x] Three-axis review, all findings fixed: GoF "leave it" (anchors are refused; a new taxonomy is rare), plus a test holding the nine tables' columns equal; Standards: a `source.yaml` naming the source and its bronze family (`company_facts`), since a suite test loads one per folder, and a plainer test placeholder; Spec: a file with facts and no CIK, facts or a taxonomy that is not an object, and a concept without a `units` object were landed or dropped silently, now refused by document assertions and `type: object, nullable: false`, one test each; a test that a fact lands whole with every field silver needs; 16 tests pass, all 368 captured files still read equal (122.6 s) (2026-10-22 18:12 ET)
- [ ] PR, CI green, merge
- [x] Learning → skill: `skills/company-financials/SKILL.md`, "Reading company facts" (the contract's file, the CIK filed two ways, every other shape refused); `CLAUDE.md`, Path ownership (run the overlap guard unpiped) (2026-10-22 18:17 ET)
