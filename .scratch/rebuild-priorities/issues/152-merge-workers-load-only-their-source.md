# 152: Merge workers load only the rules their source needs

Priority: 152. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 11:03 ET, from [ticket 32](32-profiling-08-recreation-proof.md).

Type: task. Status: resolved on merge of the PR below (Claude, branch `claude/t152-census-lazy`). Blocked by: none.

## Question

The `mdm.merge` and `mdm.publish` workers read `rules/sources/<SEC Company>/census-filer.yaml` when `name_census.py` is
imported, for every source. A rules folder without that file cannot merge anything, a GLEIF or Person batch included;
the recreation proof's second agent hit this. Should the file load only when the Name Census is used?

## Parts

- [x] A test imports the worker modules and every module a merge pins from a rules folder without the file (imports, not a full merge), and one names the file when the census is used: `tests/mdm/test_merge_worker_without_census_file.py`, failed before the fix, passes after (2026-11-01 17:31 ET)
- [x] The file loads when the Name Census is used, not at import: `sec_reading()` cached in `name_census.py`; 233 census, rules and preparation tests pass (2026-11-01 17:31 ET)
- [x] PR, CI green, merged: #1267 (the PR is the record; ticked 2026-11-04 04:42 ET)
- [x] `Learning → skill`: none; a code fix, and `tests/mdm/test_merge_worker_without_census_file.py` holds it (2026-11-01 17:33 ET)
