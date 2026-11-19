# The access audit skill and its first findings

Status: open
Type: task

Operator: "audit the setup using sox soc itsm auditor before finalising all the skills and roles", then "create this as an audit skill".
The audit skill tests 14 platform-neutral objectives through adapters for Snowflake, PostgreSQL, AWS, GitHub and the workstation, and
prints a coverage matrix (operator: "dont build the audit only for snowflake we need to use it for other platform"). The Snowflake
auditor role `EDGARTOOLS_PROD_AUDITOR` exists; AWS and GitHub ran with administrator identities because no read-only identity exists there.

First multi-platform run: 8 pass, 18 fail, 11 not tested. The skills and roles are not finalised while a high finding is open and unaccepted.

## Parts

- [x] Skill `skills/access-audit/` with its hard stops, 21 controls mapped to SOX ITGC, SOC 2 and ITIL, the rating and the finalising gate; `scripts/access_audit.py` reads Snowflake, PostgreSQL and the repository read-only (tests/unit/test_access_audit.py and the skill lints: 48 passed with the monitoring tests; run live, 2026-11-19 06:34 ET)
- [x] IND.snowflake: read-only auditor role `EDGARTOOLS_PROD_AUDITOR` (security, usage and governance viewers, monitor usage, warehouse usage) with a key-pair service user, created on the operator's word; the audit re-ran as it and passes IND (2026-11-19 06:42 ET)
- [x] Safe Snowflake batch applied on the operator's "yes" (before the ruling not to use the admin account): resource monitor `EDGARTOOLS_PROD_MONITOR` (10 credits a month, notify 75%, suspend 100%) on all three warehouses, account statement timeout 7,200 s and 600 s on the two service users, password policy on the account, key-pair-only authentication policy on the two service users; both service logins still work; the Snowflake re-audit passes TMO and fails CST until the usage view catches up (2026-11-19 06:50 ET)
- [x] The operator's overall administrator account must exist and is never used, changed or planned against: the audit refuses its connections, the remediation refuses its name and any plan that touches it (tests/unit/test_access_audit.py: 47 passed)
- [x] The Snowflake access controls as code: `infra/terraform/access/snowflake/accounts/prod` (roles, key-pair users, grants, monitor, timeouts, policies); `terraform validate` passes (2026-11-19 06:50 ET)
- [x] `access_remediate.py` (bootstrap, plan, apply with the operator's words recorded, destroy refused) so the skill closes findings itself
- [ ] Run the one-time bootstrap SQL as an account owner (the access-admin identity does not exist yet); then import the existing objects and plan
- [ ] ADM/OPS/AUT.snowflake concern the operator's own account: sign an acceptance (owner, reason, expiry) or move the work to service identities
- [ ] IND.aws and IND.github (medium): create a read-only audit identity for AWS (SecurityAudit) and a read token for GitHub; both ran as administrators
- [ ] ADM/OPS/AUT.aws and CST/LOG/POL/ROT.aws (high and medium): 1 console user without MFA, 1 user holding administrator access, 3 active keys older than 90 days, no CloudTrail trail, no account password policy; the S3 public-access block could not be read
- [ ] CHG.github (medium): the default branch has no protection, no required review and no required checks (auto-merge on green CI is the operator's ruling: record it as an accepted exception with owner and expiry, or protect the branch)
- [ ] Gaps in the matrix (`-`): PostgreSQL has no test for ADM, OPS, AUT, POL, CHG, SEC; GitHub none for LOG, CST, NET; extend the adapters or record why they do not apply
- [ ] Add the Databricks and OpenMetadata adapters when those platforms hold data
- [ ] ADM.snowflake (high): one administrator, no MFA; add a second break-glass administrator and enrol MFA for both
- [ ] OPS.snowflake (high, with AC-02): the administrator's default role is ACCOUNTADMIN; default to a working role
- [ ] OPS.snowflake (high): 2,990 of 18,523 queries in 7 days ran as ACCOUNTADMIN; run loads and tools under named least-privilege roles
- [ ] AUT.snowflake (high): 206 password-only administrator logins in 7 days; key pair or MFA, and no tool connects as the administrator
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
- [x] Learning → skill: the controls, the gate and the remediation are in access-audit; aws-snowflake-operations holds the access-identity rules (key-pair read-only users, EVENTS_VIEW, the lag, never the person's admin account, credential files by key names only); database-monitoring holds the out-of-memory reading (2026-11-19 07:02 ET)
