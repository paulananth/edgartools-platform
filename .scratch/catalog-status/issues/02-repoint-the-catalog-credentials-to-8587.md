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
- [ ] `rules catalog check` (read-only) shows whether the target Pipelines exist; publish the catalog plan if not
- [ ] `load_chain.py --catalog-status` catches the finished steps up; read each outcome
- [ ] Learning → skill: openmetadata LOCAL-SERVER, the order of initialize, publish, status
