# 171: The Dataset Contracts section is not named `mdm`

Priority: 171. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 09:38 ET (operator, 2026-11-02: "Reading rules can not be named reading[\"mdm\"]"; chosen name: `dataset_contracts`, "dataset_contracts (Recommended)").

Type: task. Status: open. Blocked by: [169](169-company-financials-run-through-bookkeeping-and-the-change-journal.md) slice 1 merging (it touches the same line of `target_manifest.py`).

## Question

Each source's rules file (`rules/sources/<source>/source.yaml`) has a top-level `mdm:` section. It holds that source's Dataset Contracts (what its records are, for master data). It is not the MDM database, and a source that writes nothing to master data (company facts) has none. The code reads it as `reading["mdm"]`, which reads as the MDM database. What is it called?

Answer: `dataset_contracts` (the CONTEXT.md term). Measured: 10 rules files, 23 Python uses in `edgar_warehouse`, 41 test lines, nothing in Rust.

## Parts

- [ ] GoF consult before any code (a rename: expect "leave the structure, rename")
- [ ] List every use first: `rg` for `["mdm"]`, `.get("mdm")`, `mdm:` in the rules files, docs and skills; separate the section key from the unrelated words (MDM database, `mdm.prepare` and `mdm.merge` operations, `MDM_DATABASE_URL`, the `mdm` catalog database), which keep their names
- [ ] Rename the key in the 10 rules files and every reader, the validators and mapping documents; an old key is refused with a message naming the new one (no silent fallback)
- [ ] Regenerate the changed Mapping Documents; the rules digests change, so say which proofs are carried forward and which rerun (none expected: no value moves)
- [ ] Tests: the affected areas by name (rules, target manifest, change journal, mapdoc, catalog, sequence); one test that a file with the old key is refused
- [ ] The `mdm-relationship-types`, bookkeeping, data-onboarding and refining-rules skills and the docs say `dataset_contracts`
- [ ] Learning → skill: the section name in the skills that teach the rules file
