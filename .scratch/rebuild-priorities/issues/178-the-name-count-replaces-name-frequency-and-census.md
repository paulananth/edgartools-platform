# 178: The Name Count replaces "Name Frequency" and "census"

Priority: 178. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 20:23 ET (operator, 2026-11-02: "remove censes and Name Frequency chang it to \"Name Count\"").

Type: task. Status: resolved (2026-11-03 06:44 ET; every part ticked). Blocks: [177](177-sec-company-loads-through-the-load-command.md) slices 3 to 5 (they write new Name Count settings, so the names change first). Related: [177](177-sec-company-loads-through-the-load-command.md).

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
- [x] Slice 4 code: the matching-profile fields (`name_count_*_field`) and the route name; the historic-digest tests restore the old words (2026-11-02 23:26 ET; tests/mdm, tests/unit, tests/architecture, tests/engine incl. the installed bundle, cargo test and the Postgres integration tests pass locally)
- [x] Slice 4 rules (2026-11-02 23:55 ET): no new merge version. Activating `platform-2026-11-03.name-count-match` was refused ("Rule version already registered with different steps": a registered rule version keeps its steps, so the function id cannot be renamed), so the id `name_census_match@1` stays as a stored identity, like the Company contract's publication-key words; the profile fields keep their new names, and the merge digest is unchanged (634a5120…), so the active `platform-2026-11-02.fresh-store` stands. The draft `platform-2026-11-03.name-count-match` stays unused
- [x] The label inside the file and `census.yaml` reads `sec-gleif-name-count-v1` (operator, 2026-11-02: "change sec-gleif-name-census-v1 sec-gleif-name-count-v1"); the built file's label is patched in place, counts unchanged (2026-11-02 21:04 ET)
- [x] Slice 5 code (operator, 2026-11-03 06:23 ET: "Rename it fully"): the stored record key `name_census` is `name_count` (landing v8 of the Company reading, migration 030 re-creates the stage index, the profile field, the combine groups, the publication key, the trail digest key `name_count`); the Name Count file needs no change (its entries carry no such key). Historic digests and the retired-mapper outcomes get the old words back through `tests/support/name_count_words.py`. tests/mdm, tests/unit, tests/architecture, all of tests/engine (installed bundle too) and the Postgres mastering and matching-route tests pass locally
- [x] Slice 5 rules and store (2026-11-03 06:43 ET): `sec.company-2026-11-03.name-count-stored-key` active in `source-by-source` (proof carried forward, approved "Approved the rules always"); `mdm migrate` applied migration 030 there (the index is `stage_record_name_count_lei`). Found: PR #1332 left 030 out of `MIGRATIONS`, so `migrate` skipped it; registered now, and `tests/unit/test_every_mdm_migration_is_applied.py` fails without it (assertion: `{'030_name_count_index.sql'} == set()`): a new `sec.company` version (landing v8), carried-forward proof, approved and activated in `source-by-source`; `mdm migrate` applies migration 030 there; the active merge version stays (its digest is unchanged)
- [x] Slice 6: the Rust crate's tests and fixtures (2026-11-03 06:43 ET): the function and fields were renamed in slices 4 and 5; the test key `__no_name_count_rows__`, the qualification README's `NAME_COUNT_BOUNDED` and `NAME_COUNT_LIMIT` and the generated header text now say Name Count; the evidence files and the scratch directory name `codex-census-eof-proof` are recorded data and stay
- [x] Final check (2026-11-03 06:44 ET): `git grep -i census` outside `.scratch/`, `.planning/` and `docs/research/` finds only: the function id `name_census_match@1` and the Company contract's words "plus the Name Census digest" (registered identities); the applied migrations 001 and 026 and migration 030's note on the old name; the `CONTEXT.md` avoid list; the proof file name `census.json` in `rules/merge/policy.yaml`; the retired-mapper oracle's input key `name_census` and `tests/support/name_count_words.py` (the old words, on purpose); two paths into `.planning/` history; the scratch directory name `codex-census-eof-proof` in the qualification evidence; `docs/specs/person/consumer.md` and the dated database design review (the word "census" meaning a population sample, not the Name Count)
- [x] Learning → skill (2026-11-03 06:44 ET): `skills/data-platform` and `skills/refining-rules` use Name Count (first part); `skills/mdm-engineering`, "Migrations": `store.MIGRATIONS` is the list that `migrate` applies (now guarded by a test), and a registered name (a rule version's steps, a Dataset Contract's key words) is an identity that a rename cannot touch
