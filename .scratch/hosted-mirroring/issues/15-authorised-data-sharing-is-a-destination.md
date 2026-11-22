# 15: The list of tables allowed to leave the stores is a destination, not a rule

Status: resolved
Type: task

Operator, 2026-11-22: "move rules/exposure.yaml to destination/authorised_(some business friendly name)". Where data may be shared is not a
rule (as Gold, ticket 12, and the sources, ticket 11, were not). The business name chosen: `authorised_data_sharing.yaml`.

## Checklist

- [x] Test first (failed: `is_file()` False for the new path; passes now) 2026-11-22 15:56 ET: `destination/authorised_data_sharing.yaml` exists and `rules/exposure.yaml` does not; fails now
- [x] `git mv rules/exposure.yaml destination/authorised_data_sharing.yaml`; its `names:` still reaches `rules/snowflake.yaml` (`names: ../rules/snowflake.yaml`) 2026-11-22 15:56 ET
- [x] Every reader follows: Gold views and `gold.yaml`, the exposure scripts and mirror SQL, the catalog readers, tests, skills and runbook text; the Gold views read `destination/<file>` 2026-11-22 15:56 ET
- [x] Packaging: the `destination` folder is already included in the package files (config only; an installed bundle was not run): `pyproject.toml` includes `destination/**/*.yaml` 2026-11-22 15:56 ET
- [x] Tests: the exposure, Gold views, catalog reader, mirror SQL and architecture unit tests pass; the catalog display digest changes once because the file leaves the rules folder: 703 unit and architecture tests pass; the one failure, `test_profiling_run.py::test_the_catalog_summary_names_and_counts_but_never_a_value` (`'draft' == 'approved'`), fails the same without this change 2026-11-22 15:56 ET
- [x] Learning → skill: name the skill line this ticket changed, or "none": none, the skills name the file by path and now carry the new path 2026-11-22 15:56 ET

## Answer

`destination/authorised_data_sharing.yaml` replaces `rules/exposure.yaml`; the Gold views, mirror SQL, catalog readers, tests and skills read the new path. Reviewed on three axes (Haiku): the stale comment was fixed and the packaging line made honest; GoF: leave it (three code sites, a resolver is worth it at a fourth move).
