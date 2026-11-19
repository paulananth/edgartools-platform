# The access audit skill and its first findings

Status: open
Type: task

Operator: "audit the setup using sox soc itsm auditor before finalising all the skills and roles", then "create this as an audit skill".
The audit skill tests 21 controls against the live Snowflake account, the PostgreSQL instance and this repository. The first run
was as an administrator (no auditor role exists), so it also fails its own independence control.

First run: 6 pass, 13 fail, 2 not tested. The skills and roles are not finalised while a high finding is open and unaccepted.

## Parts

- [x] Skill `skills/access-audit/` with its hard stops, 21 controls mapped to SOX ITGC, SOC 2 and ITIL, the rating and the finalising gate; `scripts/access_audit.py` reads Snowflake, PostgreSQL and the repository read-only (tests/unit/test_access_audit.py and the skill lints: 48 passed with the monitoring tests; run live, 2026-11-19 06:34 ET)
- [ ] AUD-00 (medium): create a read-only auditor role (security, usage and governance viewers, monitor) and a key-pair connection; re-run as it (an account change: needs the operator's word)
- [ ] AC-01 (high): one administrator, no MFA; add a second break-glass administrator and enrol MFA for both
- [ ] AC-02 (medium): the administrator's default role is ACCOUNTADMIN; default to a working role
- [ ] AC-03 (high): 2,990 of 18,523 queries in 7 days ran as ACCOUNTADMIN; run loads and tools under named least-privilege roles
- [ ] AC-04 (high): 206 password-only administrator logins in 7 days; key pair or MFA, and no tool connects as the administrator
- [ ] NW-01 (medium): no account network policy; one exists for the Postgres instance only; add an account policy and one per service user
- [ ] OP-01 (medium): 3 warehouses, 0 resource monitors; create monitors with a credit quota
- [ ] OP-02 (medium): the account statement timeout is 172,800 s; set a bound on the account or on each service user
- [ ] AU-01 (medium): no password or authentication policy
- [ ] DB-04 (high): pgaudit is off for the runtime logins; enable write and role classes, or sign an acceptance of the risk
- [ ] DB-05 (low): 6 login roles, none with a connection limit; set limits (the instance reached out-of-memory at 10 merge workers)
- [ ] CM-02 (medium): the log-reader role and user are not in Terraform; add them to `infra/terraform/access/snowflake`
- [ ] SC-01 (high): a plain-text password sits in the SnowCLI connection file for the administrator and was printed once in a session; rotate it and move the connection to key pair
- [ ] KR-01 and AR-01 (not tested): record a rotation date and owner for the log-reader key, and schedule the first access review
- [ ] Re-run the audit as the auditor role after the fixes; the gate in the skill passes
- [ ] Learning → skill: the controls and the gate are in access-audit; database-monitoring's role section points at it
