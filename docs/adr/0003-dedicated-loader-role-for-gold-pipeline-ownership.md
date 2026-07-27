# Dedicated Loader role owns the gold pipeline, separate from Deployer and Reader

On 2026-07-27, applying routine Snowflake bootstrap SQL to prod broke the manifest pipeline: the 20 `EDGARTOOLS_GOLD` dynamic tables and the 3 manifest procedures had accumulated mixed ownership (`ACCOUNTADMIN` from early ad-hoc bootstrapping, `EDGARTOOLS_PROD_DEPLOYER` from a later `dbt run`, whichever role last touched a given table). `REFRESH_AFTER_LOAD` runs `EXECUTE AS OWNER` and calls `ALTER DYNAMIC TABLE ... REFRESH`, which Snowflake requires the *direct owner* role to execute — so ownership drift silently breaks the pipeline the next time any unrelated deploy touches one of these objects.

We split Snowflake account roles three ways instead of reusing the existing two:

- **Deployer** (`EDGARTOOLS_PROD_DEPLOYER`) — creates and owns Terraform-managed infrastructure (warehouses, schemas, the dashboard app). Deployment, not data ownership.
- **Loader** (`EDGARTOOLS_PROD_LOADER`, new) — exclusively owns the `EDGARTOOLS_GOLD` dynamic tables and the manifest-pipeline procedures. `dbt run --target prod` and the manifest task always execute as this role.
- **Reader** (`EDGARTOOLS_PROD_READER`) — read-only consumption for dashboards and reports (same thing in this platform). `SELECT` only, never owns or mutates.

## Considered Options

- **Fold Loader into Deployer** (have `dbt run` keep using `EDGARTOOLS_PROD_DEPLOYER`, just apply it more consistently). Rejected: Deployer's job is to create infrastructure via Terraform runs that touch many unrelated objects; every such run is another chance for gold-table ownership to drift again, which is the exact failure this incident traced back to. A role whose *only* job is owning the pipeline's data objects can't be perturbed by an unrelated infra change.
- **Ad hoc `ACCOUNTADMIN` ownership** as a stopgap. Rejected outright — broadest-possible privilege for a narrow, repeatable job, and explicitly ruled out during the incident.

## Consequences

Ownership-transfer grants must always use `COPY CURRENT GRANTS`, never `REVOKE CURRENT GRANTS` — the latter strips *all* downstream grants on the object (it briefly broke `EDGARTOOLS_PROD_READER`'s dashboard access during this same incident, caught and fixed). `infra/scripts/deploy-snowflake-stack.sh --run-dbt` still resolves its dbt role from Terraform's `role_names.deployer` output, not `EDGARTOOLS_PROD_LOADER` — Terraform doesn't manage the Loader role yet, so automated prod dbt runs will re-flip ownership until that's reconciled (tracked as a follow-up, not done in the same session as the incident).
