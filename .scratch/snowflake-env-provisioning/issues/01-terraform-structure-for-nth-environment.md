# Decide Terraform structure for standing up an Nth independent Snowflake environment

Type: grilling
Status: resolved

## Question

The current Terraform layout is one hand-built directory per environment
(`infra/terraform/snowflake/accounts/dev`, `.../prod`, each with its own
hardcoded `terraform.tfvars` pointing at a specific org/account) and a
matching pair under `infra/terraform/access/snowflake/accounts/{dev,prod}`.
The map's destination requires standing up a 3rd, 4th, Nth **genuinely
independent** Snowflake account (not another database inside the same
account, like dev/prod were) without hand-copying and hand-editing a new
directory each time.

Resolve: should new independent environments be represented as

(a) a **new directory per account** under `infra/terraform/.../accounts/`,
    but with tfvars **generated** from a parameter set / config file instead
    of hand-edited (keeps today's mental model: one root per account, `ls
    accounts/` shows every environment); or

(b) a **single parameterized module/workspace pattern** (e.g. Terraform
    workspaces, or one root that takes an account-identifying var file as
    input) that stands up any environment from the same code path without a
    new directory per account; or

(c) something else — e.g. Terraform Cloud/CDKTF-style generation, or
    per-account state isolation via a wrapper script that still emits (a)
    under the hood.

This decision shapes the naming/parameter contract every other ticket in
this map (02, 03, 04) needs to code against, so it should resolve first
among the open frontier tickets where practical.

Consider: existing precedent elsewhere in this repo for parameterizing
per-environment infra (e.g. how `infra/scripts/deploy-aws-application.sh`
already parameterizes `--env`), blast-radius isolation (should one
account's `terraform apply` ever be able to touch another's state), and how
much this repo's current tooling (`go-live.sh`, `deploy-snowflake-stack.sh`)
would need to change under each option.

## Answer

**Structure: option (a) — generated directory-per-account.** Each
independent environment keeps its own Terraform root under
`infra/terraform/snowflake/accounts/<env-name>/` (and the matching
`infra/terraform/access/snowflake/accounts/<env-name>/`), each with its own
state file. This preserves full blast-radius isolation — one account's
`terraform apply` structurally cannot reach another's state — which matters
concretely in this repo: CLAUDE.md's AWS-teardown 5-whys documents a real
incident where a stale backend pointer nearly let a destroy run against the
wrong account's resources. It also requires the least change to existing
tooling (`go-live.sh`, `deploy-snowflake-stack.sh` already assume
"one directory per environment"), and avoids introducing Terraform
workspaces, a pattern with zero precedent anywhere else in this repo.

The one change from today: `terraform.tfvars` and `backend.hcl` inside each
new directory are **generated** from a small parameter set / config file
(org, account name, account locator, region, storage-integration ARNs, etc.)
rather than hand-copied from `dev`/`prod` and hand-edited. This is what
actually delivers "no code changes to add environment N+1" — a generator
step in front of the existing per-directory root, not a rearchitecture of
how Terraform is invoked.

**Environment identifier: a free-form slug.** The string that names the
directory (`accounts/<slug>/`), the generated config file, and what scripts
accept as `--env-name` is an operator-chosen, human-meaningful name (e.g.
`secondary`, `eu-west`, `eu-prod`) — not derived from the Snowflake account
name/locator. This matches how `dev`/`prod` are named today (role-based, not
account-identifier-based) and means the identifier survives an account
being renamed or migrated without forcing a directory rename. The actual
Snowflake account name/locator/org still live inside that environment's
generated config as data, not as the identifier itself.

This resolves the naming/parameter contract Tickets 03 and 04 need: an
environment is identified by `--env-name <slug>`, which resolves to
`accounts/<slug>/` and a generated tfvars file — replacing the closed
`dev|prod` enum everywhere.

## Implementation (landed on `claude/snowflake-env-generator`)

- `infra/terraform/templates/snowflake_env/{provisioning,access}/` — templates
  derived from the live prod roots. `providers.tf`/`versions.tf` are copied
  verbatim (already fully variable-driven, verified to contain no environment
  references); `main.tf`/`variables.tf`/`outputs.tf` are `.tmpl` files using
  `{{PLACEHOLDER}}` tokens, which cannot collide with Terraform's own `${...}`.
- `infra/scripts/generate-snowflake-env.py` — pure generator (config in, files
  out; never shells out to `terraform`/`aws`/`snow`). Refuses to overwrite an
  existing root without `--force`, and fails closed on a bad slug, a missing
  field, or a partial `native_pull` block.
- `infra/terraform/environments/<slug>.json` — the parameter set, gitignored
  (carries Snowflake account identifiers, which this repo never commits);
  `example.json.example` is the tracked template.
- `tests/architecture/test_snowflake_env_generator.py` — 36 tests.

**Existing `accounts/prod` and `accounts/dev` were deliberately not touched.**
Generalizing them in place would have meant proving a no-op with
`terraform plan` against live prod, where a wrong name derivation is a
rename — and a rename of a Snowflake role or warehouse is a *replace*, not a
drift. Instead the parity test
(`test_generating_prod_reproduces_live_prod_identifiers`) reads prod's real
`main.tf` and asserts the generator, run with slug `prod`, reproduces its six
identity-bearing locals exactly. It fails if either side moves, and needs no
credentials. This is sound as far as *naming* goes because `var.environment`
reaches the modules only through `comment` strings — every actual resource name
arrives via an explicit `*_name` variable, so those six locals are the whole
naming-identity surface.

**Scope limit — the parity test is not a substitute for a full `terraform
plan` against prod, and `accounts/prod` must not be regenerated from this
template.** The template `count`-gates the `mdm_dashboard` module (see
decision 2 below) while prod's live root declares it unconditionally, so
generating slug `prod` produces the address `module.mdm_dashboard[0]` where
prod's state holds `module.mdm_dashboard` — a state-address change, which
`terraform plan` would render as destroy/create of the whole dashboard module.
Regenerating prod would require a `terraform state mv` first. This costs
nothing today (nothing regenerates prod) and is pinned by
`test_template_mdm_dashboard_count_diverges_from_live_prod` so it can't be
silently rediscovered later.

**Known duplication to keep in step:** `providers.tf`/`versions.tf` are copied
verbatim into the template, so the template now holds a *second* copy of the
Snowflake provider version pin (`= 2.14.1`). Bumping the provider in the
existing roots means bumping it in the template too — the one piece of drift
this design does not eliminate.

Three things the implementation had to decide that the grilling didn't cover:

1. **`expected_database_name` is prod-pinned by a `validation` block**, not just
   a default. Rather than drop that guard, the template generates a per-environment
   equivalent (`EDGARTOOLS_<SLUG>`), preserving the safety intent generically.
2. **The `mdm_dashboard` module is now `count`-gated and defaults off.** Prod has
   it unconditionally; dev deliberately lacks it because the MDM_GRAPH_REVIEW
   contract needs a prior generation-scoped `sync-graph` + `graph-activate` run.
   A brand-new account is in dev's position, so an unconditional module would
   make its very first apply fail.
3. **Slugs are hyphen-separated lowercase, with hyphens mapped to underscores**
   for Snowflake identifiers (`eu-prod` → `EDGARTOOLS_EU_PROD`), since hyphens
   are illegal in unquoted Snowflake identifiers. Underscores are rejected in
   the slug itself so `eu-prod` and `eu_prod` cannot collide onto one database.

Verified offline: both generated roots pass `terraform fmt -check` and
`terraform init -backend=false && terraform validate` (Terraform 1.15.8); the
full 375-test architecture suite passes.
