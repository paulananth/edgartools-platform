# Map: One-shot brand-new-Snowflake-account → fully-live provisioning script

Labels: wayfinder:map

## Destination

A generic, reusable, fully-parameterized script (or tightly chained set of
scripts) that takes a brand-new, empty Snowflake account and stands up a
fully independent, prod-shaped environment covering: the source/native-pull
layer (feeds gold), gold (8 dynamic tables + dbt), MDM (Snowflake-native
Postgres operational store), and Neo4j (Graph Analytics Native App +
sync/verify pipeline). The script provisions its own Terraform state S3
bucket as part of the one-shot flow. Nothing is hardcoded — org, account,
region, instance names, and resource names are all parameters (or a config
file), so the same tooling can stand up a 3rd/4th/Nth independent
environment later without code changes.

## Notes

- **Trigger:** `snowconn` was just pointed at a genuinely new Snowflake
  account (org/account identifiers deliberately not recorded here — this is a
  public repo; see `~/.snowflake/connections.toml`, connection `snowconn`) —
  confirmed live, working (`snow sql --connection snowconn`). Confirmed via
  grilling this is **not** a replacement for the decommissioned dev
  environment (see CLAUDE.md's "Snowflake DEV is DECOMMISSIONED" section,
  2026-07-29) — it's a second, fully independent prod-like environment.
- **AWS-side is an explicit precondition, not built here.** S3 buckets
  (bronze/warehouse/export), IAM role ARN for the storage-integration trust
  relationship, SNS topic ARN for manifest events, and the Step
  Functions/ECS compute that actually runs the warehouse ETL against this
  new account are all assumed to already exist elsewhere. This script only
  needs their ARNs/names supplied as parameters (matching the existing
  `native_pull` module's variable shape: `snowflake_storage_role_arn`,
  `snowflake_export_root_url`, `snowflake_manifest_sns_topic_arn`).
- **Terraform state bucket creation IS in scope** (unlike the rest of the
  AWS side above) — the script provisions its own tfstate S3 bucket as a
  bootstrap step, since "one-shot" means not depending on a bucket someone
  set up by hand beforehand.
- **Credential/auth approach stays as-is, explicitly out of scope.**
  Password-based `TF_VAR_snowflake_password` sourced from
  `~/.snowflake/connections.toml`, same as today. Not a target for this
  effort (a real gap, but a separate one).
- Source/native-pull layer presence in gold's scope is not a real fork — it's
  the same Terraform root/module (`native_pull`) that already builds gold's
  prerequisites, so it travels with the gold ticket rather than needing its
  own decision.
- Existing building blocks this effort reuses/generalizes rather than
  replaces: `infra/scripts/go-live.sh` (wizard, walks Terraform roots),
  `infra/scripts/deploy-snowflake-stack.sh` (post-Terraform Snowflake
  objects: manifest task, dbt, dashboard), `infra/scripts/bootstrap-prod-mdm.sh`
  (MDM Postgres instance — currently `--env` is a hardcoded `dev|prod` enum),
  `infra/terraform/snowflake/accounts/{dev,prod}` +
  `infra/terraform/access/snowflake/accounts/{dev,prod}` (current
  per-account Terraform roots, hardcoded tfvars).
- Skills to consult per ticket: `/grilling` + `/domain-modeling` for
  architecture-shaped tickets; `/research` for anything requiring primary
  Snowflake documentation (e.g. Native App installation semantics).

## Decisions so far

- [Can the Neo4j Graph Analytics Native App be installed on a brand-new Snowflake account without manual UI steps?](issues/02-neo4j-native-app-install-scriptability.md) — No: a one-time, per-organization Snowsight step (ORGADMIN accepting the Provider and Consumer Terms) is unavoidable and undocumented as scriptable; once cleared, the actual install is real SQL (`CREATE APPLICATION ... FROM LISTING`), and while there's no typed Terraform resource for it, the provider's `snowflake_execute` escape hatch can run it inside a Terraform root if preferred over a separate SQL/SnowCLI step.
- [Decide Terraform structure for standing up an Nth independent Snowflake environment](issues/01-terraform-structure-for-nth-environment.md) — Generated directory-per-account: each environment keeps its own Terraform root (blast-radius isolation, minimal tooling change) but `terraform.tfvars`/`backend.hcl` are generated from a config file instead of hand-copied; environments are identified by an operator-chosen free-form slug (e.g. `secondary`), not the Snowflake account name/locator.
- [Generalize scripts hardcoded to a dev|prod environment enum](issues/03-generalize-env-enum-scripts.md) — All 4 scripts move from `--env <dev|prod>` to `--env-name <slug>` (validated against the real Terraform directory, not a whitelist) plus a required, explicit `--snow-connection <name>` with no default derivation; clean breaking rename, no back-compat shim, since dev is decommissioned and only prod's call sites need updating.
- [Define the AWS-side precondition contract this script requires](issues/04-aws-side-precondition-contract.md) — The contract is actually 4 values, not 3: `snowflake_storage_role_arn`, `snowflake_manifest_sns_topic_arn`, `snowflake_export_root_url` (all three already surfaced together by `access/aws/accounts/<env>`'s Terraform outputs — pull via `terraform output -json`, don't hand-derive), plus `storage_external_id`, which is coordinated by naming convention across both AWS and Snowflake roots rather than wired as a dependency. Surfaced a real, deferred gap: the AWS-side roots are themselves still hardcoded per-environment, same enum problem Ticket 03 just fixed on the Snowflake side.
- [Decide end-to-end provisioning run order across source-native-pull → gold → MDM → Neo4j](issues/05-provisioning-run-order.md) — Adopt `go-live.sh`'s existing, already-tested 13-stage sequential wizard as-is rather than designing a new order; surfaced a real gap (stage 9 grants against the Neo4j Native App but never installs it) and fixes it with a new "Neo4j Native App install" stage inserted early, right after stage 1, so its slow manual ORGADMIN Marketplace-terms step overlaps with the unrelated stages 2-8 instead of stalling the wizard mid-run. **Correction recorded during implementation:** installing the app is necessary but not sufficient — the grants stage also runs before `mdm sync-graph` creates the schema it grants on, which is [Ticket 07](issues/07-graph-grants-before-schema-ordering.md).
- [Decide what "fully live" is verified by](issues/06-fully-live-verification.md) — MDM/graph/AWS already have real automated checks; gold is the one gap (stage 11's row-count "verification" is just an operator-facing echo, not an automated check). Close it with a standalone CLI command (mirroring `mdm verify-graph`) that fails if any expected gold table is empty, called from a new final go-live.sh stage after stage 14. Dashboard reachability explicitly out — gold correctness implies dashboard correctness, and checking it directly means solving Streamlit-in-Snowflake's session-auth problem for disproportionate value.

## Not yet specified

(none — every fog item identified while charting this map has either resolved
into a decision above or graduated to Out of scope. Ticket 07 is a *new* open
ticket surfaced during implementation, not residual fog: it is stated precisely
enough to work.)

## Out of scope

- AWS-side infrastructure provisioning (S3 buckets, IAM roles, SNS topics,
  Step Functions/ECS) for source ingestion — documented as a precondition,
  not built by this effort.
- Credential/auth hardening (e.g. moving off password auth to keypair auth)
  — current password-based auth stays as-is.
- Replacing/restoring the decommissioned dev environment — confirmed via
  grilling this new account is a separate, independent prod-like
  environment, not a dev replacement.
- How the eventual warehouse compute (ECS tasks, Step Functions that
  actually write bronze/silver/gold data) gets pointed at this new
  Snowflake account — this is compute/AWS-side configuration, which
  [Ticket 04's answer](issues/04-aws-side-precondition-contract.md) confirms
  sits entirely on the AWS-side precondition, already ruled out of scope
  above. Graduated out of "Not yet specified" once Ticket 04 made it precise
  enough to see it's beyond this map's destination, not sharp enough to
  belong inside it.
