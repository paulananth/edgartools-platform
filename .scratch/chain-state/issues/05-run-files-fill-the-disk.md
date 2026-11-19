# Run files of dropped stores and verified runs filled the disk

Status: open
Type: bug

The readiness disk check failed (27 GiB free against 100). `~/.local/share/edgartools/hosted-prod/manifests/load` held 220 GB:
378 run folders (185 GB) from runs before the reset, whose Bookkeeping store the reset had dropped, and 58 (31 GB) from the load after
it. No step deleted a run's files: not the reset that dropped the stores, not a load once its run was verified.

## Parts

- [x] Measure: 436 run folders, 378 before the reset (185 GB), 58 after (31 GB); a run folder is almost all prepared bundle data, its `reports` under 1 MB. 2026-11-19 18:41 ET
- [x] Operator: "This needs to be cleaned up immediately". The 378 run folders from before the reset deleted after checking no load ran and every path was a run folder: 214 GiB free. 2026-11-19 18:41 ET
- [x] Operator: "make it part of runbook and loads". A load deletes a bundle's files once its run is verified complete (a run that stops keeps them, to resume): `tests/unit/test_rules_loading.py::test_each_new_bundle_is_prepared_submitted_and_driven` failed with "assert not True" (the run folder was still there); `test_a_bundle_whose_run_stops_keeps_its_files_so_the_run_can_resume` passes before and after. 2026-11-19 18:41 ET
- [x] The reset deletes the dropped stores' run files (`<manifest root>/load`) and keeps the extracts: `tests/unit/test_reset_hosted_databases.py::test_a_reset_deletes_the_run_files_of_the_stores_it_drops_and_keeps_the_extracts` failed with "has no attribute 'clear_run_files'". 8 reset tests, 58 loading and driving tests pass. 2026-11-19 18:41 ET
- [x] Runbook (init.md, Databases step) and data-operations `HOSTED-LOADS.md` ("Run files") say both. 2026-11-19 18:41 ET
- [ ] A run that stopped and was finished by a later load keeps its folder until the next reset (the load does not know its folder); left as it is unless it is seen to grow
- [ ] Merge the PR when CI is green
- [x] Learning → skill: data-operations `HOSTED-LOADS.md`, "Run files". 2026-11-19 18:41 ET
