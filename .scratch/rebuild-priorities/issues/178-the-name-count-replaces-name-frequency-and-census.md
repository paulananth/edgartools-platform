# 178: The Name Count replaces "Name Frequency" and "census"

Priority: 178. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 20:23 ET (operator, 2026-11-02: "remove censes and Name Frequency chang it to \"Name Count\"").

Type: task. Status: open (in progress). Blocks: [177](177-sec-company-loads-through-the-load-command.md) slices 3 to 5 (they write new Name Count settings, so the names change first). Related: [177](177-sec-company-loads-through-the-load-command.md).

## Question

`CONTEXT.md` called the pinned count of how many SEC filers and GLEIF legal entities carry each name "Name Frequency" and said to avoid "Census" and "Name Census". The code, the rules files and the stored file all say "census". The operator asked for one word: **Name Count**, and no "census".

## What counted (read 2026-11-02 20:23 ET, outside `.scratch/` and `.planning/`, which are history and stay as written)

- 93 files and 749 lines say "census"; 29 files say "Name Frequency".
- Two Python modules (`name_census.py`, `name_frequency.py`), the CLI `mdm name-census` and its `--name-census` flag.
- Eighteen rules files: `rules/sources/sec.company/census*.yaml` and `combine-census*.yaml`, `rules/sources/gleif/census-*.yaml`.
- The merge policy function `name_census_match` (the policy language), in `rules/merge`.
- The stored Name Count file (its keys, its `version`) and the contract tokens that carry its digest.
- Python, engine and Rust tests and fixtures (`tests/engine`, `tests/mdm`, `crates/source-contract/tests`).
- Mapping Document workbooks and the Data Catalog, which print the names.

## Rules for the rename

- A rules file that moves changes its source's digest, so a source version saved under the old names is a new version; no old file is edited in place.
- The stored Name Count file is a versioned contract: the new names come with a new version of the file, and a file built under the old version is rebuilt (the load needs a rebuilt one anyway).
- `.scratch/` and `.planning/` stay as written.

## Parts

- [x] The glossary and the prose: `CONTEXT.md` defines **Name Count** (avoid "Name Frequency", "Name Census", "Census"); the skills and the living docs say Name Count wherever they name the concept; file names, commands and code identifiers stay until the slices below (2026-11-02 20:23 ET; lints pass)
- [x] Slice 2: the Python modules (`name_count.py`, `name_count_file.py`), the CLI (`mdm name-count`, `--name-count`), their functions and tests; the contract strings (rules file names, the record trail key `name_census`, the policy function) stay for slices 3 to 5 (2026-11-02 21:04 ET; tests/mdm, tests/unit, tests/architecture and tests/engine pass locally; the Postgres tests run in CI)
- [x] Slice 3: the 16 rules files of `sec.company` and `gleif` renamed (`name-count-*.yaml`, `combine-name-count*.yaml`), their references, the step, slot and group names (`name_count`, `name_count_names`, `name_count_digest`, `name_count_cascade`) and their prose; the Mapping Documents regenerated; the historic digest test restores the one renamed word (2026-11-02 22:21 ET; tests/mdm, tests/unit, tests/architecture, tests/engine incl. the installed bundle, and the Company mastering and matching-route integration tests pass locally)
- [x] New version of `sec.company` (`sec.company-2026-11-03.name-count-rules-files`) for the renamed rules files and the `census.yaml` label, with its carried-forward proof, approved and activated in `source-by-source` (`gleif` is not registered in that store) (2026-11-02 23:26 ET: carried-forward proof, approved "Approved the rules always", active in `source-by-source`). Found 2026-11-02 22:35 ET: the Dataset Contract's `publication_key` text is protected ("Dataset identity is immutable within one source code"), so its words "plus the Name Census digest" stay as stored; the one "Census" the final check may find
- [x] Slice 4 code: the policy function `name_count_match@1` (Rust, Python, rules, policy language), the matching-profile fields (`name_count_*_field`) and the route name; the historic-digest tests restore the old words (2026-11-02 23:26 ET; tests/mdm, tests/unit, tests/architecture, tests/engine incl. the installed bundle, cargo test and the Postgres integration tests pass locally)
- [ ] Slice 4 rules: the merge rules' new version with its carried-forward proof, approved and activated in `source-by-source`
- [x] The label inside the file and `census.yaml` reads `sec-gleif-name-count-v1` (operator, 2026-11-02: "change sec-gleif-name-census-v1 sec-gleif-name-count-v1"); the built file's label is patched in place, counts unchanged (2026-11-02 21:04 ET)
- [ ] Slice 5: the stored Name Count file's keys and version, and the tests that read it
- [ ] Slice 6: the Rust crate's tests and fixtures
- [ ] Final check: `git grep -i census` outside `.scratch/` and `.planning/` finds only words that mean something else (the N-CEN form, a filename tally)
- [ ] Learning → skill: `skills/data-platform` and `skills/refining-rules` use Name Count (done in the first part), or "none"
