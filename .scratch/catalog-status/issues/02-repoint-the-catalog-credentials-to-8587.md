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
- [ ] The operator chooses how the surviving catalog gets credentials this session can use, one of: (1) the path of the private env
  file the runtime that started it used (loaded in a subshell, never read or printed) , recommended; (2) reset the administrator
  password in the running stack (changes that runtime's login); (3) recreate the instance fresh (`edgartools-openmetadata_*` volumes
  deleted, the catalog published again): destroys its catalog data
- [ ] `rules catalog check` (read-only) shows whether the target Pipelines exist; publish the catalog plan if not
- [ ] `load_chain.py --catalog-status` catches the finished steps up; read each outcome
- [ ] Learning → skill: openmetadata LOCAL-SERVER, the order of initialize, publish, status
