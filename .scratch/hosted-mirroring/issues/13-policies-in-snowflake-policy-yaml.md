# 13: Credential policies come from snowflake_policy.yaml and live in no database of their own

Status: open
Type: task

Operator, 2026-11-21: "you cannot be creating a database you have to use native platform feature the policy must be kept in the snowflake_policy.yaml and it must be audited remove creating unapproved db do research in snowflake documentation".
Research (Snowflake documentation, CREATE PASSWORD POLICY, CREATE AUTHENTICATION POLICY, Working with passwords): both policies are schema-level objects, created with CREATE ... POLICY on a schema and applied with ALTER ACCOUNT; the documentation names no account-level form, and the built-in password policy cannot be edited. So a policy needs a schema, and the schema goes in a database the platform already has.

## Checklist

- [x] Research: policies are schema-level objects; a database is required, so the native answer is a schema in an existing database 2026-11-21 08:13 ET
- [x] `rules/snowflake_policy.yaml`: the values and the home (schema `POLICIES` of the Gold database named in `snowflake.yaml`), with the operator's words 2026-11-21 08:13 ET
- [x] Terraform: `snowflake_database.governance` is gone; the schema, password policy and authentication policy are made from the file in the Gold database. `tests/architecture/test_access_terraform_creates_no_database.py` (2 pass; the old file declared a database, so it would have failed) 2026-11-21 08:13 ET
- [x] Audit: control POL also fails on any difference between the live policies and the file (a value, a missing policy, a policy in another database or schema). Tests failed first (AttributeError, no `policy_drift`), 53 pass 2026-11-21 08:13 ET
- [x] Skills: access-audit POL row, and the access-finding procedure in aws-snowflake-operations says no database is created for a control 2026-11-21 08:13 ET
- [ ] Apply (operator's words): the next access plan creates the schema and both policies in the Gold database, re-attaches them to the account, and drops the old `EDGARTOOLS_GOVERNANCE` database (a destroy: needs `--allow-destroy` and its own approval); not run: nothing was applied or read from Snowflake
- [ ] Re-run the audit on `snowflake`: POL passes once the policies sit in the Gold database and equal the file
- [ ] Learning → skill: done in the two skills above; remove this line when the apply is recorded
