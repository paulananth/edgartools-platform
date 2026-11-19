# Readiness did not cover the whole deployment

Status: open
Type: bug

The load started when the nine-check gate passed. Three things the runbook covers were not in the gate, and a skipped step was written off wrongly.

## Parts

- [x] The catalog step (runbook step 8) was skipped as "no catalog file is set up" without reading why; the file existed and the catalog had drifted by 21 differences. Published and checked: `confirmed`. 2026-11-19 12:08 ET
- [x] The chain's state file was not read by the gate: a stale marker made the first scheduler start end at once (fixed in the state verdict; the gate now shows the verdict and the done-step count). `STATE` check. 2026-11-19 12:08 ET
- [x] Each duty file's login was not tested by the gate. `LOGINS` check (names only, a driver's text is never kept); live read: all four duty files answer. 2026-11-19 12:08 ET
- [x] The catalog is now a check (`CATALOG`: confirmed, or no catalog configured). 2026-11-19 12:08 ET
- [x] Tests: `tests/unit/test_readiness.py` (a failed login, an unreadable or adopted state file, a drifted or unreadable catalog each close the gate; no catalog and a file to be set aside do not). 2026-11-19 12:08 ET
- [x] Learning → skill: data-operations `HOSTED-LOADS.md` and the init runbook (the gate is not the runbook; say which steps ran). 2026-11-19 12:08 ET
- [ ] The administrator password (`snowflake_admin`) printed once by a check script that gave a `+psycopg2` URL to the raw driver (the case `CONNECTIONS.md` already warns about). A Postgres `ALTER ROLE` is refused on the platform-managed login: the operator resets it with `ALTER POSTGRES INSTANCE ... RESET ACCESS FOR 'snowflake_admin'` and the provisioner rewrites `owner.env`.
- [ ] Merge the PR when CI is green
