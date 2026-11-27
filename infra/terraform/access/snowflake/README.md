# Snowflake access controls as code

`accounts/prod` holds the read-only roles and key-pair service users the access audit relies on (`EDGARTOOLS_PROD_LOG_READER`,
`EDGARTOOLS_PROD_AUDITOR`), the monthly credit monitor and the account statement timeout. It is applied by the access-admin service identity, never by a person's administrator account.

```bash
python skills/access-audit/scripts/access_remediate.py bootstrap     # once: the access-admin identity and its key pair
python skills/access-audit/scripts/access_remediate.py plan          # what would change; refuses a destroy
python skills/access-audit/scripts/access_remediate.py apply --words "<the operator's words>"
python skills/access-audit/scripts/access_audit.py                   # the re-audit
```

Objects made by hand before this root existed are imported once (`terraform import`), so a plan shows no change for them:
the two roles and users, the database owner role with its grant and the Gold database's ownership, the operations database's ownership, the monitor and the grants. No credential policy is kept: every platform login is a
`TYPE = SERVICE` user, which Snowflake never lets sign in with a password.
Warehouses are not managed here: attaching the monitor to a warehouse stays an `ALTER WAREHOUSE` until the warehouses are
imported as resources.
