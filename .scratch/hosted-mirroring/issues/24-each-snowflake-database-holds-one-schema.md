# 24: Gold holds one schema; no credential policy object; the ingress rule in an operations database

Status: open
Type: task
Owner: claude (operator, 2026-11-26: "gold must not have control and ploicies schemas only one schema")

The Gold database held four schemas, read live as the audit identity: `GOLD`, `CONTROL` (the hosted Postgres ingress network rule
`MDM_POSTGRES_INGRESS_ALL` and the audit's policy reader procedure), `POLICIES` (the password policy on the account, the key-pair-only
authentication policy on the 4 service users) and Snowflake's default `PUBLIC`. Snowflake keeps a policy and a network rule only inside
a schema; it has no database-free form of either.

## Checklist

- [x] Operator, 2026-11-26, on where the credential policies go: "credential policies must not be in a db it has to live outside"; then, on dropping both policies with the administrator's password on Snowflake's built-in rules (minimum 8 characters, not 14): "Yes, drop them (Recommended)" (2026-11-26 21:23 ET)
- [x] Operator, 2026-11-26, on the ingress rule, which lets the loader and the mirror reach the Postgres store: "An approved operations db" (2026-11-26 21:23 ET)
- [x] `rules/snowflake.yaml`: `operations` names `EDGARTOOLS_OPERATIONS` with its one schema `CONTROL` and the operator's words; `rules/snowflake_policy.yaml` deleted (no reader left, by `git grep`) (2026-11-26 21:23 ET)
- [x] Access Terraform: the policies' schema, both policies, the three attachments, the reader procedure and its grant removed; the operations database's ownership and the auditor's USAGE on it declared; `terraform validate` passes; `test_the_access_root_keeps_no_credential_policy_and_no_schema` failed on the old root (`assert ['snowflake_p...y_attachment'] == []`) and passes (2026-11-26 21:23 ET)
- [x] `one_schema_sql.py` prints the move from the names file: the new rule, the policy naming both rules then the new one, the old rule dropped; each policy detached from the account and every user before its drop; the named schemas and each database's `PUBLIC` dropped; a kept schema, a schema outside the platform databases, a rule left in a kept schema and a name that is not a plain identifier refused (`tests/unit/test_one_schema_sql.py`, 8 pass) (2026-11-26 21:23 ET)
- [x] Access audit: POL passes when the usage views list no password policy and no attached authentication policy and every `EDGARTOOLS` login is a service user; SCH now covers Snowflake, each database the names file gives a schema holding only that one, not tested when one cannot be read (`tests/unit/test_access_audit.py`, 59 pass). Live, as the audit identity: 1 password policy and 1 authentication policy (4 attachments) counted; the Gold database's extra schemas `CONTROL`, `POLICIES`, `PUBLIC` (2026-11-26 21:23 ET)
- [ ] Live move, run by an administrator (agents never use the administrator account): the output of `one_schema_sql.py` with the live names (the network policy `EDGARTOOLS_PROD_MDM_POSTGRES_POLICY`, the rule in `EDGARTOOLS_GOLD.CONTROL`, the two policies in `EDGARTOOLS_GOLD.POLICIES`, the 4 service users, the auditor role, `--drop-schema EDGARTOOLS_GOLD.CONTROL --drop-schema EDGARTOOLS_GOLD.POLICIES`); compare its first `DESCRIBE` with the new rule's values before the policy changes
- [ ] After the move: a loader connection to the store succeeds; `SHOW SCHEMAS` lists only `GOLD` in Gold and only `CONTROL` in operations; the access audit's POL and SCH pass (the usage views lag by hours)
- [ ] `terraform import` of the operations database's ownership and the auditor's grants with the next access apply
- [x] Learning → skill: `aws-snowflake-operations/SKILL.md` (each platform database holds one schema, no credential policy object, the ingress rule in the operations database, `one_schema_sql.py`); `access-audit/SKILL.md` (POL and SCH on Snowflake, policies counted in the usage views) (2026-11-26 21:23 ET)
