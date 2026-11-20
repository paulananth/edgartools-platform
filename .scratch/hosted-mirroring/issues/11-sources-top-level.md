# 11: Sources live at the top level, not under rules

Status: claimed
Type: task

The operator, 2026-11-20: "it cannot be under rules this is part of source and source mapping", then "move rules/sources/ to top level sources/".
A pure move, in its own PR: 134 files, 210 references in 105 files. The mirror's system of record (it belongs in the source mapping, as a
`managed_mirror` flag on each silver table spec or on `source.yaml`: an open question) waits for this.

Baseline taken before the move (the merge policy digest, the catalog's rules digest, and each source's rules version): all must be identical after it,
or every file reprocesses and the hosted registered policy stops matching.

## Checklist

- [x] No open PR of another runtime touches `rules/sources/` (checked with `gh pr list`: none) 2026-11-20 18:38 ET
- [x] Baseline digests recorded before the move: the merge policy digest, the catalog's rules digest and each of the 19 sources' rules version 2026-11-20 18:38 ET
- [x] Consult `/gof-refactor-reviewer` (Haiku): one resolver, the sibling-of-rules-root rule stated in its docstring and copied by `skill install --rules`; no environment variable 2026-11-20 18:38 ET
- [x] Test first: `tests/architecture/test_sources_path_has_one_owner.py` failed while 20 modules built a sources path; it passes now (2 tests) 2026-11-20 18:38 ET
- [x] `git mv rules/sources sources` (134 files); `rules.files.sources_root` is the one resolver and raises when the folder is missing; every site in the package calls it 2026-11-20 18:38 ET
- [x] The merge policy digest and all 19 sources' rules versions are identical after the move; the catalog's display digest differs only because the comments that said `rules/sources` now say `sources` 2026-11-20 18:38 ET
- [x] Packaging: `pyproject.toml` include, the data-skill wheel's `sources` mapping, `bundle.py` (`doctor` reports the sources folder, `skill install --rules` copies `sources` beside the rules), both Dockerfiles 2026-11-20 18:38 ET
- [x] Text: `rules/sources` became `sources` in code, tests, skills, docs and the exposure list's `requirement` paths; `rules_change_guard` reads changed paths under `sources/` 2026-11-20 18:38 ET
- [x] Tests: unit, architecture and mdm 2,862 passed; 15 integration files that read sources passed on PostgreSQL; the committed Mapping Documents equal their regenerated ones (`test_every_committed_mapping_document_equals_its_rules`) 2026-11-20 18:38 ET
- [ ] The installed-bundle engine tests (`tests/engine/test_data_skill_bundle_postgres.py`) install the wheels from the committed HEAD by URL: run in CI on this PR
- [ ] Open: `rules/managed-mirror.yaml` (PR 1965) is still under rules; it is replaced in the mirror's own change, not this one
- [ ] Learning → skill
