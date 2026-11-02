# 165: Quality cases show the engine's results

Priority: 165. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 06:45 ET (same request as 163).

Type: task. Status: resolved for silver checks; source checks and master limits deferred. Blocked by: none.

## Question

The 29 cases have no pass or fail, so the Data Quality tab shows nothing run. Where does the engine record a failed check, and can the publisher send a result per case?

## Parts

- [x] Found where the engine records failed checks (2026-11-02 08:01 ET): a silver table's `quality` column lists the failed check ids per flagged row; a source check with `on_fail: exception` sets the record aside with reason `quality_<id>` in MDM. Local state: no silver store is connected (the connection files only unset it), and the shared MDM store shows no exception or quality table to the verifier login. The only measured counts in the repo are `failed_rows` on OpenFIGI profile proposals, which are not configured cases
- [x] Decided with the operator (2026-11-02 08:01 ET): `publish` sends the results ("Should publish send the results Yes")
- [x] Results source decided (2026-11-02 08:11 ET, operator: "Agreed" to a results file written by the engine's run): `checks.run` reports `rows_checked`; a silver load given `QUALITY_RESULTS_FILE` keeps the latest report per check; `publish --results` sends one result per case and `check --results` reads it back (`tests/unit/test_rules_catalog.py::test_publish_sends_each_recorded_result_to_its_case_and_check_reads_it_back`, `tests/unit/test_silver_quality_results.py`, 77 pass on a rebuilt engine)
- [x] The result API proven live with a throwaway case on a real table: status, timestamp and row counts read back as sent; the probe case and its suite deleted, 46 cases (2026-11-02 08:11 ET)
- [ ] ~~Results for the source (`mdm`) checks and the master identifier limits~~ deferred to a new ticket: their counts come from the MDM run report (`quality.profile`) and exceptions, not the silver writer
- [ ] ~~Live: a real silver load's results shown on the Data Quality tab~~ deferred: no silver store is connected on this machine
- [x] GoF consult before the code: leave `land`/`checks.run`, add one small module (2026-11-02 08:15 ET)
- [x] Three-axis review (2026-11-02 08:15 ET): GoF, applied two of three (no plan mutation in `publish`; the results file loaded once), kept the environment variable because several callers call `land`; Spec, applied row-count comparison in `check`, a clear error for a corrupt file, a refusal of a result that fails more rows than it checked, and tests for the writer hook and the CLI flag; Standards, tightened the vague FQN test and hoisted an import. Kept as judgement calls: a results entry is a plain dict, and a delivery in several parts overwrites the file entry (it holds the latest delivery, not the load total)
- [x] Learning → skill: `skills/openmetadata/SKILL.md` has the result API, the results file and the probe rule (2026-11-02 08:11 ET)
