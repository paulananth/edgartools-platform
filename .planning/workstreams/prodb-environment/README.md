# prodb environment — a second production-shaped build in account 690839588395

## Why this exists

The user asked to "sync dev and prod AWS, MDM, Neo4j, and Snowflake" and then,
after discussion, to "spin up production using go-live.sh" in AWS account
`690839588395` — the account this session has working credentials for.

The **real** production environment already exists, fully launched (see
`.planning/workstreams/go-live/STATE.md` — milestone v1.6, Release Owner GO
2026-06-26), in a **separate AWS account (`077127448006`)**, with its own
Snowflake role/connection (`edgartools-prod`, not configured in this session).
This session only has credentials for `690839588395` (the dev account) and
the `snowconn` Snowflake connection.

Standing up `go-live.sh --env prod` naively against those credentials does
**not** reach the real prod — it builds a second, same-named environment
inside the dev account and (for Snowflake) the dev Snowflake account, which
already hosts the real `EDGARTOOLS_PROD` database. Two hard collisions
surfaced immediately:

1. `edgartools-prod-tfstate` and the other `edgartools-prod-*` S3 buckets are
   already owned by the real prod account, globally, in S3's account-independent
   namespace.
2. `EDGARTOOLS_PROD` (database), `EDGARTOOLS_PROD_DEPLOYER` (role), etc.
   already exist in the **same Snowflake account** `snowconn` connects to —
   confirmed via `SHOW DATABASES LIKE 'EDGARTOOLS%'` before touching anything.
   Proceeding with the stock naming would have targeted the real production
   Snowflake database, not a new one.

Per user direction, this build uses a distinct naming prefix — **`prodb`** —
for every resource whose name would otherwise collide with, or be
indistinguishable from, the real prod's resources. `--env prod` (the literal
flag value) is still used where scripts require it for *behavioral* reasons
(e.g. `WAREHOUSE_ENVIRONMENT=prod` production safety lockdowns) — only
*naming* changed, not environment semantics.

**This is not the real production environment.** It is a second,
prod-shaped build for exercising the `load_history`-era data-architecture
fixes (see the `claude-data-architecture-fixes` workstream / PR #114) against
production-scale infrastructure and Step Functions, without touching the real
prod account or database.

## Architecture overview

This build follows the exact same layered architecture documented in
`docs/data-architecture.md` — nothing about the *logical* data pipeline
(bronze -> silver -> MDM -> gold -> Snowflake -> dashboard) changes between
dev, real prod, and prodb. What differs is purely the AWS/Snowflake resource
names and the account/database they live in. This section maps that logical
architecture onto the concrete prodb resources built so far.

```text
AWS account 690839588395 (shared with dev)
  |
  +-- Passive infra (Terraform: infra/terraform/accounts/prod)
  |     VPC, 2 public subnets, security group, S3 buckets (prodb-named),
  |     ECS cluster, ECR repo, CloudWatch log group, SNS topic, KMS key,
  |     empty Secrets Manager containers
  |
  +-- Access/runtime roles (Terraform: infra/terraform/access/aws/accounts/prod)
  |     sec_platform_prodb_runner_{execution,task,step_functions} IAM roles,
  |     scoped inline policies (bucket/secret ARNs), Snowflake storage-reader
  |     role + SNS topic policy (native-pull trust)
  |
  +-- Active application (infra/scripts/deploy-aws-application.sh, no Terraform)
        5 ECS task definitions (small/medium/large/mdm-small/mdm-medium),
        23 Step Functions state machines, manifest infra/aws-prodb-application.json

Snowflake account IXKYQWK-YW12138 (shared with dev and REAL prod)
  |
  +-- Baseline + native-pull (Terraform: infra/terraform/snowflake/accounts/prod)
  |     EDGARTOOLS_PRODB database, EDGARTOOLS_SOURCE/EDGARTOOLS_GOLD schemas,
  |     EDGARTOOLS_PRODB_REFRESH_WH/_READER_WH warehouses, 17 source tables,
  |     file formats, external S3 stage, manifest pipe/stream, stored
  |     procedures, EDGARTOOLS_DASHBOARD schema + STREAMLIT app + internal stage
  |
  +-- Access control (Terraform: infra/terraform/access/snowflake/accounts/prod)
  |     EDGARTOOLS_PRODB_{DEPLOYER,REFRESHER,READER} roles + all grants,
  |     read from snowflake/accounts/prod's remote state -- no hardcoded names
  |
  +-- Imperative (not Terraform-managed): SNOWFLAKE_RUN_MANIFEST_TASK,
        created/replaced by deploy-snowflake-stack.sh's own `snow sql` call
        every deploy, RESUMEd, 1-minute schedule

Not yet built (stages 7-14): dbt gold models, Streamlit dashboard upload,
Snowflake Postgres MDM instance, MDM secret bootstrap, bronze data (prodb's
S3 bronze bucket is empty -- no dev->prodb sync tooling exists), MDM
connectivity/run/sync/verify, end-to-end smoke test.
```

Every resource name, role, and database above is prodb-specific and
independently verified live (see "Live resource inventory" below) --
none of it is the real prod's `077127448006` account or `EDGARTOOLS_PROD`
Snowflake database.

## Naming scheme

| Concern | Real prod (untouched, account 077127448006) | This build (account 690839588395) |
|---|---|---|
| AWS S3 buckets | `edgartools-prod-tfstate`, `-bronze`, `-warehouse`, `-snowflake-export` | `edgartools-prodb-tfstate`, `-bronze`, `-warehouse`, `-snowflake-export` |
| AWS ECS cluster, ECR repo, Secrets Manager, SNS, KMS, CloudWatch | `edgartools-prod-*` | `edgartools-prod-*` (unchanged — account-scoped, not globally namespaced, so no actual collision with a *different* AWS account; left as-is rather than surgically renaming every nested Terraform module) |
| AWS IAM runner roles | `sec_platform_runner_execution`, `_task`, `_step_functions` | `sec_platform_prodb_runner_execution`, `_task`, `_step_functions` (these are NOT namespaced by environment upstream — see Fix 1 below — and dev already owns the un-prefixed names in this account with dev-scoped policies) |
| Snowflake database | `EDGARTOOLS_PROD` | `EDGARTOOLS_PRODB` |
| Snowflake roles/warehouses | `EDGARTOOLS_PROD_DEPLOYER`, `_REFRESHER`, `_READER`, `_REFRESH_WH`, `_READER_WH` | `EDGARTOOLS_PRODB_*` |
| `--env` flag value passed to scripts | `prod` | `prod` (unchanged — behavioral, not identity) |

## Fixes made to the underlying scripts/Terraform (not just workarounds)

These are real gaps in the infrastructure code, found and fixed here, not
just papered over for this one build. All are backward-compatible defaults
that leave dev (and, by extension, real prod's already-working `--env prod`
invocations without the new override flags) completely unchanged.

1. **`infra/terraform/access/aws/modules/runtime_access/variables.tf` +
   `main.tf`** — added `runner_role_name_prefix` (default `"sec_platform"`,
   preserving today's exact dev behavior with zero change) so the
   `sec_platform_runner_*` IAM role names can be distinguished when two
   environments share an AWS account. Before this fix, `terraform apply` for
   a second environment in the same account would either collide on
   `EntityAlreadyExists`, or (worse, if manually imported) silently reuse a
   role whose attached policy is scoped to the *other* environment's exact
   resource ARNs — AccessDenied at runtime, not at plan time. Verified by
   reading the actual attached policy on the live `sec_platform_runner_execution`
   / `sec_platform_runner_task` roles: both are scoped to literal
   `edgartools-dev-*` ARNs.
2. **`infra/terraform/accounts/prod/terraform.tfvars`** (created, was
   missing) — sets `bronze_bucket_name`/`warehouse_bucket_name`/
   `snowflake_export_bucket_name` overrides to `edgartools-prodb-*` (these
   variables already existed in `variables.tf`, just needed values).
3. **`infra/terraform/access/aws/accounts/prod/main.tf`** — added
   `runner_role_name_prefix = "sec_platform_prodb"` to the `runtime_access`
   module call (this file only; `accounts/dev/main.tf` untouched).
4. **`infra/terraform/snowflake/accounts/prod/main.tf`** — changed the
   hardcoded `EDGARTOOLS_PROD`/`EDGARTOOLS_PROD_DEPLOYER`/etc. locals to
   `EDGARTOOLS_PRODB`/`EDGARTOOLS_PRODB_DEPLOYER`/etc. This was the most
   serious of the four: this root has no override mechanism at all
   (unlike the AWS passive-infra root, which already had bucket-name-override
   variables) and `deploy-snowflake-stack.sh --env prod` runs
   `terraform apply` against it directly with no `-var` overrides possible —
   running it unmodified would have applied real changes against the
   literal `EDGARTOOLS_PROD` Snowflake database.
   `infra/terraform/access/snowflake/accounts/prod/main.tf` needed no
   separate fix — it reads `database_name`/`role_names` from this root's
   remote state outputs, so the fix cascades automatically (confirmed live:
   its Terraform plan pulled `EDGARTOOLS_PRODB_*` names with no edits here).
5. **`infra/scripts/deploy-aws-application.sh`** — this script doesn't just
   *default* to the `sec_platform_runner_*` role names, it actively
   **rejects** any ARN whose role name doesn't literally match
   (`require_runner_role_name()`), with no override flag. This directly
   conflicted with fixes 1/3 above: having correctly renamed the roles via
   Terraform, this script then refused to deploy against them (`ERROR:
   --execution-role-arn must reference IAM role sec_platform_runner_execution;
   got .../sec_platform_prodb_runner_execution`). Added a
   `--runner-role-name-prefix <prefix>` flag (default `sec_platform`, same
   default and zero dev impact as fix 1) that the script uses to derive all
   three expected role names, mirroring the Terraform module's
   `runner_role_name_prefix` variable. Passed `--runner-role-name-prefix
   sec_platform_prodb` for this build.
   (Separately: the `WARNING: neither s3://edgartools-prod-bronze nor
   s3://edgartools-prod-bronze-<account> exists...` lines that print even
   when `--bronze-bucket-name` etc. are passed explicitly are harmless noise,
   not a bug — bash evaluates all arguments to `first_nonempty(...)` before
   the function runs, so `resolve_bucket_name`'s discovery probe (and its
   warning) always fires; the explicit CLI value still wins because
   `first_nonempty` returns the first non-empty argument, which is the
   explicit flag, not the probe result.)
6. **`infra/scripts/deploy-snowflake-stack.sh`'s `load_password_from_snow_config()`**
   — treated a set `SNOWFLAKE_PASSWORD` env var as "a password is already
   available, nothing to do," but only `TF_VAR_snowflake_password` actually
   feeds the Terraform Snowflake provider (`providers.tf`:
   `password = var.snowflake_password`). With only `SNOWFLAKE_PASSWORD` set
   (this operator's shell has it, presumably for `snow`/dbt convenience) and
   `TF_VAR_snowflake_password` unset, the function silently returned without
   setting either, so Terraform ran with a null password and failed
   (`Error: open snowflake connection: 390100 (08004): Incorrect username or
   password was specified.`). Fixed by explicitly propagating
   `SNOWFLAKE_PASSWORD` → `TF_VAR_snowflake_password`/`DBT_SNOWFLAKE_PASSWORD`
   in that branch instead of silently no-op'ing. Verified the fix by sourcing
   the function in isolation and comparing lengths/equality only — never
   printed the password value.
   Separately (not a code bug, an environment fact worth recording): this
   operator's shell has a `SNOWFLAKE_PASSWORD` env var whose value does
   **not** match the `snowconn` SnowCLI connection's stored password
   (confirmed by length comparison only, never printed — 7 vs. 14
   characters). Fix 6 makes that env var authoritative when set, per the
   script's documented "environment variables take precedence" contract, so
   this build's actual applies were run with `env -u SNOWFLAKE_PASSWORD -u
   TF_VAR_snowflake_password` to force the (known-good) SnowCLI config.toml
   fallback instead. Whether the shell's `SNOWFLAKE_PASSWORD` is simply
   stale or intentionally different is outside this build's scope to judge —
   flagging it here so a future session doesn't waste time rediscovering it.

## Known Terraform/imperative tool tension (pre-existing, not fixed here)

`terraform plan` against `infra/terraform/snowflake/accounts/prod` will
**always** show a pending in-place update to
`module.native_pull[0].snowflake_task.manifest_processor`
(`SNOWFLAKE_RUN_MANIFEST_TASK`), even immediately after a clean deploy.
Root cause: `deploy-snowflake-stack.sh` explicitly documents this task as
"not managed by Terraform" and issues its own `CREATE OR REPLACE TASK ...
RESUME` via `snow sql` right after the Terraform applies finish, so the two
tools' views of the same object permanently disagree (Terraform's managed
resource vs. the imperative recreate). This is pre-existing behavior in
shared code, not introduced by this build, and (based on a same-pattern
comment already in the script) likely shows the same drift in real prod
today. Not a functional problem — the task is correctly `started` with the
right schedule/definition after every deploy — just don't mistake this one
resource's perpetual plan diff for real configuration drift.

## Gaps identified, not yet fixed (tracked for follow-up)

- **`go-live.sh` has no `--name-prefix`/`--db-name-prefix` concept at all.**
  Every fix above was applied by hand-editing the environment-specific
  Terraform `main.tf`/`.tfvars` files directly, then running each stage's
  underlying commands directly rather than through `go-live.sh deploy
  --apply` (which has no way to pass these overrides through its stages).
  A proper fix would thread a `--name-prefix` option through
  `go-live.sh build_stages()`, `deploy-aws-application.sh` (already supports
  `--name-prefix` for general resources and now `--runner-role-name-prefix`
  for runner roles specifically — just needs go-live.sh to pass both
  through), and `deploy-snowflake-stack.sh` (has no override flag at all
  today; this build hand-edited `snowflake/accounts/prod/main.tf`'s locals
  instead).
- **No dev→prod (or dev→prodb) bronze sync tooling exists.** Stage 11
  (`bronze_seed_silver_gold`) assumes bronze data already exists in the
  target environment's S3 bucket ("cold-starting *or recovering* ... from a
  bronze snapshot that's already in S3"). The go-live workstream's own
  STATE.md documents this exact gap as launch gate matrix row 13, "stays
  BLOCKED... run manually whenever bronze parity with dev is needed" — no
  script for it exists anywhere in the repo (confirmed by search). prodb's
  `edgartools-prodb-bronze` bucket is currently empty; this is the next
  concrete blocker once stages 7-10 are done.
- **No DSN auto-extraction between go-live.sh stages 9 and 10.** Stage 9
  creates the Snowflake Postgres instance and prints its connection info via
  `DESCRIBE POSTGRES INSTANCE ... --format JSON`; stage 10 needs
  `SNOWFLAKE_APPLICATION_MDM_DSN` set from that output but go-live.sh doesn't
  parse/pass it automatically — the operator (or, here, this session) has to
  read stage 9's JSON output and construct the DSN by hand.
- **The `snowflake` root's dashboard `STREAMLIT` object has a genuine
  cross-root circular dependency, not automated by the wrapper.** On a cold
  start, `snowflake/accounts/prod`'s full apply creates the STREAMLIT object
  before `access/snowflake/accounts/prod` has granted the owning role access
  to its backing stage, so the very first apply fails with `092804 (42501):
  The specified stage DASHBOARD_SRC does not exist or the current role does
  not have access`. This is not new to prodb — it's already documented (and
  was manually resolved the same way) in the real prod launch's own evidence
  file, `.planning/workstreams/go-live/phases/07-production-snowflake-native-pull-and-gold/evidence/native-pull.md`
  item 6. Recovery sequence (used here, exit 0 both times): (1) apply
  `access/snowflake` — succeeds for every resource except its own last grant,
  which needs Streamlit to exist; (2) apply `snowflake` root targeted at just
  `module.dashboard.snowflake_streamlit.dashboard` — now succeeds, since
  step 1 already granted the deployer/reader/refresher roles to SYSADMIN;
  (3) re-apply `access/snowflake` — its one remaining grant now succeeds;
  (4) full `snowflake` root apply to confirm no drift remains. Not fixed at
  the wrapper level (would require restructuring which root owns the
  dashboard resource, or a real cross-root dependency mechanism Terraform
  doesn't have natively) — documenting the recovery here so it doesn't need
  rediscovering a third time.

## Live resource inventory (independently verified, not just deploy-log output)

Verified directly against AWS/Snowflake APIs, not just trusted from script
output:

**AWS (`690839588395`, `us-east-1`):**
- S3: `edgartools-prodb-tfstate`, `-bronze`, `-warehouse`, `-snowflake-export` (bronze is empty — see gaps above)
- VPC `vpc-0b2a820945cfc0109`, 2 public subnets, security group `sg-0f7de61f13ba27744`
- ECS cluster `edgartools-prod-warehouse`; 5 active task definition families: `edgartools-prod-{small,medium,large,mdm-small,mdm-medium}` (revision 2)
- ECR repo `edgartools-prod-warehouse`
- 23 Step Functions state machines, all prefixed `edgartools-prod-` (full list: `bootstrap`, `bootstrap-batched`, `bootstrap-full`, `bronze-seed-silver-gold`, `catch-up-daily-form-index`, `daily-incremental`, `full-reconcile`, `gold-refresh`, `load-daily-form-index-for-date`, `load-history`, `mdm-backfill-relationships`, `mdm-check-connectivity`, `mdm-counts`, `mdm-gold`, `mdm-migrate`, `mdm-run`, `mdm-seed-from-silver`, `mdm-seed-universe`, `mdm-sync-graph`, `mdm-verify-graph`, `ownership-mdm-gold`, `silver-mdm-gold`, `targeted-resync`)
- Secrets Manager: `edgartools-prod-edgar-identity`, `edgartools-prod-runner-credentials`, `edgartools-prod/mdm/{api_keys,neo4j,postgres_dsn,snowflake}` (MDM secrets still hold placeholder values — stage 10)
- IAM roles: `sec_platform_prodb_runner_{execution,task,step_functions}`, `edgartools-prod-snowflake-s3`
- SNS topic `edgartools-prod-snowflake-manifest-events`, KMS key aliased `edgartools-prodb-snowflake-export`
- Terraform drift check (plan-only, all 4 applied roots): `accounts/prod` clean; `access/aws/accounts/prod` shows a plan-only false positive (reverts the Snowflake trust principal to the bootstrap wildcard because a bare `terraform plan` can't reproduce the wrapper's reconcile-pass overlay variables — the actually-applied state is already correctly reconciled, confirmed by the wrapper's own last "No changes" run); `snowflake/accounts/prod` shows only the expected manifest-task tension described above; `access/snowflake/accounts/prod` clean.

**Snowflake (account `IXKYQWK-YW12138`, shared with dev and real prod):**
- Database `EDGARTOOLS_PRODB`; schemas `EDGARTOOLS_SOURCE`, `EDGARTOOLS_GOLD`, `EDGARTOOLS_DASHBOARD`
- Warehouses `EDGARTOOLS_PRODB_REFRESH_WH`, `EDGARTOOLS_PRODB_READER_WH`
- Roles `EDGARTOOLS_PRODB_{DEPLOYER,REFRESHER,READER}`, all granted to SYSADMIN with the documented grant set
- 17 source tables, 2 file formats, external S3 stage `EDGARTOOLS_SOURCE_EXPORT_STAGE`, manifest pipe + stream, 3 stored procedures, `SNOWFLAKE_RUN_MANIFEST_TASK` (`started`, 1-minute schedule)
- Storage integration `EDGARTOOLS_PRODB_EXPORT_INTEGRATION`; native-pull validation artifact confirms `native_pull_ready: true` (`infra/snowflake/sql/prod_native_pull_handshake.json`, copy/stage counts both 0 — expected, no data loaded yet)
- Dashboard schema, internal stage `DASHBOARD_SRC`, and `STREAMLIT` app `EDGARTOOLS_DASHBOARD` all created (after the circular-dependency recovery above)

## Status log

- **Stages 1-4 (bootstrap-state, AWS passive infra, AWS access/runtime roles,
  Snowflake baseline+access)**: DONE.
- **Stage 5 (ECS task defs + Step Functions)**: DONE. Blocked twice, both
  fixed at root cause (see Fixes 5 above and Terraform fixes 1/3): first on
  missing bucket/role/cluster overrides, then on the hardcoded
  runner-role-name validation.
- **Stage 6 (Snowflake native-pull foundation)**: DONE. Blocked twice, both
  fixed at root cause: the password-propagation bug (Fix 6) and the
  cross-root STREAMLIT circular dependency (documented above, same recovery
  as real prod's own launch). `native_pull_ready: true`, verified live, zero
  drift outside the one known pre-existing Terraform/imperative tension.
- **Stages 7-14**: not started (dbt gold, Streamlit dashboard upload,
  Snowflake Postgres/graph prerequisites, MDM secret bootstrap, bronze
  backfill, MDM connectivity/run/sync/verify, AWS MDM E2E, smoke test).
  Bronze backfill (stage 11) is the next expected hard blocker per the gaps
  section above.
