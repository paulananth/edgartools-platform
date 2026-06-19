# MDM Production Secrets Runbook

This runbook documents the `aws secretsmanager put-secret-value` commands for
populating the two production MDM secrets — `edgartools-prod/mdm/postgres_dsn`
and `edgartools-prod/mdm/snowflake` — as required by D-05/D-06 before any
production MDM connectivity, migration, or E2E checks can run.

**Every value below is a `<PLACEHOLDER>` token.** No real secret values, DSNs,
ARNs, passwords, or `put-secret-value` / `get-secret-value` command output are
pasted here. The operator replaces each `<PLACEHOLDER>` with the real production
value at runtime, in a shell environment, without committing the value.

See `01-LAUNCH-GATE-MATRIX.md` rows 22-25 for the acceptance gates that depend
on these secrets being populated.

---

## 1. Populate `edgartools-prod/mdm/postgres_dsn` (via validated helper script)

The `infra/scripts/bootstrap-aws-mdm-secrets.sh` script validates the DSN
structure (scheme, host-suffix, database, `sslmode=require`) before writing
to Secrets Manager. Use the `--dsn-stdin` flag to supply the connection string
via stdin (never as a shell argument, which would appear in process listings and
shell history).

```bash
# Validates DSN scheme/host-suffix/database/sslmode before writing
# (host suffix default: .snowflake.app; database default: mdm)
printf '%s' "postgresql://<APPLICATION_ROLE_USER>:<APPLICATION_ROLE_PASSWORD>@<PROD_SNOWFLAKE_POSTGRES_HOST>.snowflake.app:5432/mdm?sslmode=require" | \
  bash infra/scripts/bootstrap-aws-mdm-secrets.sh \
    --env prod \
    --aws-profile aws-admin-prod \
    --aws-region us-east-1 \
    --dsn-stdin
# Writes to: edgartools-prod/mdm/postgres_dsn
# --dry-run flag available to validate without writing.
```

**DSN shape reference (D-07 — structure only, no values):**

```
postgresql://<user>:<password>@<host>.snowflake.app:<port>/<database>?sslmode=require
```

Structural invariants enforced by `bootstrap-aws-mdm-secrets.sh` and by
`infra/scripts/audit-mdm-snowflake-postgres-cutover.py`'s
`validate_snowflake_postgres_dsn()`:

- `<host>` must end with `.snowflake.app` (`--expected-host-suffix`, default `.snowflake.app`)
- `<database>` must equal `mdm` (default; `--database` overridable)
- Query string must include `sslmode=require`

The masked dev DSN structure captured by plan 03-01 under the evidence heading
`### Dev postgres_dsn Shape Reference (D-07 — for plan 03-02)` in
`../01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md`
is the format reference for what the prod value must look like — structure only,
no values.

---

## 2. Populate `edgartools-prod/mdm/snowflake` (raw `put-secret-value`)

No helper script exists for this secret. Populate it via the raw AWS CLI command
with a JSON `--secret-string` containing exactly the 7 uppercase keys consumed by
`_snowflake_setting()` in `edgar_warehouse/mdm/export.py` (lines 181-189).

```bash
# JSON keys consumed by _snowflake_setting() via secret.get("MDM_SNOWFLAKE_<KEY>")
# or secret.get("DBT_SNOWFLAKE_<KEY>") (uppercase keys checked first).
aws secretsmanager put-secret-value \
  --profile aws-admin-prod \
  --region us-east-1 \
  --secret-id edgartools-prod/mdm/snowflake \
  --secret-string '{
    "MDM_SNOWFLAKE_ACCOUNT": "<ORGNAME-ACCOUNTNAME>",
    "MDM_SNOWFLAKE_USER": "<PROD_MDM_SNOWFLAKE_USER>",
    "MDM_SNOWFLAKE_PASSWORD": "<PROD_MDM_SNOWFLAKE_PASSWORD>",
    "MDM_SNOWFLAKE_DATABASE": "<EDGARTOOLS_PROD>",
    "MDM_SNOWFLAKE_WAREHOUSE": "<EDGARTOOLS_PROD_REFRESH_WH>",
    "MDM_SNOWFLAKE_SCHEMA": "EDGARTOOLS_GOLD",
    "MDM_SNOWFLAKE_ROLE": "<EDGARTOOLS_PROD_DEPLOYER>"
  }'
# Output text only (no --output text needed; put-secret-value returns ARN/VersionId
# metadata to stdout by default — do NOT paste this output into evidence, it
# contains the secret ARN. Redirect to /dev/null or capture+discard if running live.)
```

Note: `MDM_SNOWFLAKE_SCHEMA` defaults to `EDGARTOOLS_GOLD` and is not a
placeholder — the prod gold schema name is known. All other `<PLACEHOLDER>`
values must be replaced with real prod credentials.

---

## 3. Not required: `edgartools-prod/mdm/neo4j`

Not required — legacy graph container. The Snowflake-hosted graph does not use
this secret; the external Neo4j/Aura path was removed from the MDM E2E
orchestration (see `docs/aws-mdm-snowflake-postgres-cutover.md`). No population
command for this go-live.

---

## 4. Deferred: `edgartools-prod/mdm/api_keys`

Deferred — purpose unclear. No population command this phase. Revisit when
the consumer is identified (see CONTEXT.md "Deferred Ideas").

---

## 5. Presence-check verification for both required secrets (D-08)

Run `describe-secret` to confirm the secret containers exist. This is a
**non-secret metadata check only** — it reveals `Name`, `ARN`,
`LastChangedDate`, and `VersionIdsToStages` but never the secret value itself.
This output is safe to record as evidence (D-08).

```bash
aws secretsmanager describe-secret \
  --profile aws-admin-prod --region us-east-1 \
  --secret-id edgartools-prod/mdm/postgres_dsn \
  --query '{Name:Name,ARN:ARN,LastChangedDate:LastChangedDate,VersionIdsToStages:VersionIdsToStages}'

aws secretsmanager describe-secret \
  --profile aws-admin-prod --region us-east-1 \
  --secret-id edgartools-prod/mdm/snowflake \
  --query '{Name:Name,ARN:ARN,LastChangedDate:LastChangedDate,VersionIdsToStages:VersionIdsToStages}'
```

A populated secret has a `VersionIdsToStages` entry with stage `AWSCURRENT`
pointing at a version created by `put-secret-value` above (i.e.,
`LastChangedDate` advances and `VersionIdsToStages` is non-empty). An
empty/never-populated container (Terraform-created) has no `AWSCURRENT` version
with a written value.

Record the `describe-secret` metadata output in
`evidence/mdm-hosted-graph.md` as proof that containers exist and have been
populated (D-08). The `describe-secret` metadata output is the only output
safe to commit.

---

## Security Note

**The operator must NOT paste `put-secret-value` response output or
`get-secret-value --query SecretString` output into any evidence or planning
file.** The response from `put-secret-value` contains the secret ARN and
VersionId — it is not a secret value, but it creates an operational linkage
that should not live in committed Markdown. The output of
`get-secret-value --query SecretString` contains the raw secret value and is
never safe to commit.

Only `describe-secret` metadata (`Name`, `ARN`, `LastChangedDate`,
`VersionIdsToStages`) is safe to record in evidence. See
`01-LAUNCH-GATE-MATRIX.md` "Secret-Safety Rules" for the full policy.

---

## References

- `infra/scripts/bootstrap-aws-mdm-secrets.sh` — DSN-validated helper for `postgres_dsn`
- `infra/scripts/audit-mdm-snowflake-postgres-cutover.py` — `validate_snowflake_postgres_dsn()` invariant enforcement
- `infra/terraform/modules/warehouse_runtime/main.tf` — Terraform-managed secret container definitions
- `edgar_warehouse/mdm/export.py` — `_snowflake_setting()` (lines 181-189): JSON key resolution order (`MDM_SNOWFLAKE_*` → `DBT_SNOWFLAKE_*` → connections.toml)
- `01-LAUNCH-GATE-MATRIX.md` row "MDM Snowflake Postgres secret container and connectivity" (row 22)
