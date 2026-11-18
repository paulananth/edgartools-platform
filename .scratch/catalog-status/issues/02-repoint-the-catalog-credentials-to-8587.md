# Repoint the catalog credentials to the surviving stack (port 8587)

Status: open
Type: task

The private repo-root `.env` names port 8585 and a token of the retired stack. The repository's tooling targets port 8587.

## Parts

- [x] The operator's word was given ("approved"). The credential bootstrap was run on its own, without `docker compose up`, so no
  container was recreated, into a new private file outside Git (`~/.config/edgartools/openmetadata.env`, mode 0600): the login
  with the vendor's default bootstrap password failed with HTTP 401, so the stack on 8587 was already bootstrapped by the runtime
  that started it (from its own worktree, whose compose file is the one the containers were created from), with an administrator
  password this session does not have. Stopped: nothing was reset or recreated. The file I had created (a generated password that
  matches nothing) was deleted (2026-11-18 10:27 ET; the helper's own answer: `OpenMetadata POST failed (HTTP 401)`). The two `.env` files that
  name port 8585 (the main checkout's and an older worktree's) hold the deleted server's login and are untouched
- [x] The operator chose option 3, "3": recreate the instance fresh, knowing it deletes the catalog's data (2026-11-18 10:33 ET): the project's four
  containers and two volumes (`edgartools-openmetadata_db-data`, `_es-data`) were deleted and nothing else (the AutoOntology and local
  test-store containers and volumes remain), then the documented `init.sh` ran with `OPENMETADATA_ENV_FILE` pointing at a new private
  file outside Git (`~/.config/edgartools/openmetadata.env`, mode 0600): the stack came up healthy, the credential helper answered
  `confirmed` for version 2.0.7 with the login and a token saved, and the initializer ran
- [x] The chain finds the catalog's private file by `OPENMETADATA_ENV_FILE`, then `~/.config/edgartools/openmetadata.env`, then the checkout's
  `.env` (2026-11-18 10:33 ET; `test_the_catalogs_private_file_is_found_by_the_variable_then_the_private_folder_then_the_checkout`: `catalog_env_file` did
  not exist)
- [x] The catalog plan was published to the fresh instance and read back with no differences: 8 domains, 8 glossaries, 31 terms, 80 assets,
  63 quality cases, 3 products, 114 pipelines (2026-11-18 10:36 ET; `rules catalog publish`, 695 write requests, `readback` differences: none)
- [x] The first catch-up published nothing: every step read "not published" within a second. The five whys: the status command did not
  start (this worktree's environment lacked the `edgar-warehouse` executable, so `uv run` could not spawn it); the outcome said only
  "no readable answer" because the command's error output was discarded; and the steps the lanes re-ran logged only "already loaded", so
  their logs named no run to publish. Fixed (2026-11-18 10:36 ET; 94 tests, each failing first): `EDGAR_WAREHOUSE` names the executable
  (`test_the_engine_is_the_executable_the_operator_names_else_uv`); an unreadable answer names its cause from the command's last error line,
  addresses hidden (`test_an_answer_that_cannot_be_read_names_why_from_the_commands_last_error_line`); a step with no run in any log uses
  Bookkeeping's own newest completed run for its source and target (`test_the_latest_completed_run_of_a_source_and_target_comes_from_bookkeepings_own_rows`,
  `test_a_step_with_no_run_in_any_log_falls_back_to_bookkeepings_latest_for_its_source_and_target`)
- [ ] `rules catalog check` (read-only) shows whether the target Pipelines exist; publish the catalog plan if not
- [ ] `load_chain.py --catalog-status` catches the finished steps up; read each outcome
- [ ] Learning → skill: openmetadata LOCAL-SERVER, the order of initialize, publish, status
