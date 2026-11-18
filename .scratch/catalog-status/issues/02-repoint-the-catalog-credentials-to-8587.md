# Repoint the catalog credentials to the surviving stack (port 8587)

Status: open
Type: task

The private repo-root `.env` names port 8585 and a token of the retired stack. The repository's tooling targets port 8587.

## Parts

- [ ] The operator's word to initialize the surviving catalog (`bash infra/openmetadata/init.sh`: it runs `docker compose up` from the
  main checkout's compose file and writes the administrator login and a 30-day token to `.env`) and to repoint `OPENMETADATA_URL`
  to 8587; check first that `up` leaves the running containers alone (the stack was started from another worktree)
- [ ] `rules catalog check` (read-only) shows whether the target Pipelines exist; publish the catalog plan if not
- [ ] `load_chain.py --catalog-status` catches the finished steps up; read each outcome
- [ ] Learning → skill: openmetadata LOCAL-SERVER, the order of initialize, publish, status
