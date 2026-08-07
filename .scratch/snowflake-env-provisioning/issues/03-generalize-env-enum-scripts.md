# Generalize scripts hardcoded to a dev|prod environment enum

Type: grilling
Status: resolved

Blocked by: 01

## Question

Several scripts this effort needs to reuse currently hardcode their
environment parameter to exactly two values:

- `infra/scripts/bootstrap-prod-mdm.sh` — `--env <dev|prod>`, rejects
  anything else (`[[ "$ENVIRONMENT" == "dev" || "$ENVIRONMENT" == "prod" ]]`)
- `infra/scripts/deploy-snowflake-stack.sh` — `--env <dev|prod>`, same enum
  check, and derives `SNOW_CONNECTION="edgartools-${ENVIRONMENT}"` by
  default (string-building a connection name from the enum)
- `infra/scripts/go-live.sh` — `--env <dev|prod>`, `default_snow_connection_for_env()`
  hardcodes `snowconn` for dev / `edgartools-prod` for prod specifically
- `infra/scripts/create-deployer.sh` — `<env>` positional arg, same `dev|prod` shape

A third independent environment (e.g. the new account behind the `snowconn`
connection, or a future Nth one) doesn't fit either bucket. Resolve: how
should these scripts' environment parameter model change to accept an
arbitrary environment/account identifier instead of the closed enum —
e.g. replace `--env <dev|prod>` with an orthogonal pair like `--env-name
<identifier>` + `--snow-connection <name>` (already a separate flag in two
of these scripts) with no default derivation, or something else? Depends on
Ticket 01's Terraform structure decision for what "environment identifier"
should even look like (a directory name? an account locator? a free-form
slug?).

## Answer

**Parameter model:** all 4 scripts replace `--env <dev|prod>` (and
`create-deployer.sh`'s `<env>` positional) with `--env-name <slug>`, where
`<slug>` is Ticket 01's free-form identifier. Validation changes from a
hardcoded `[[ "$X" == "dev" || "$X" == "prod" ]]` string check to a
directory-existence check against `infra/terraform/snowflake/accounts/<slug>/`
(and the matching `access/snowflake/accounts/<slug>/`) — an environment is
valid iff its generated Terraform root exists, so adding environment N+1
never requires touching these scripts again.

`--snow-connection <name>` becomes **required and explicit** in all 4
scripts, with **no default derivation** from `--env-name`. This directly
closes a live inconsistency already on record: `go-live.sh`'s
`default_snow_connection_for_env()` and `deploy-snowflake-stack.sh`'s
`SNOW_CONNECTION="edgartools-${ENVIRONMENT}"` string-build currently
produce *two different* default connection names for the same environment
(documented in CLAUDE.md's SnowCLI-connection-naming note) — removing
default derivation removes the disagreement instead of picking a side.

**Backward compatibility: clean breaking rename, no `--env` alias.** Since
dev Snowflake is fully decommissioned (CLAUDE.md, 2026-07-29) and prod is
the only live environment, the actual blast radius is small and known —
`prod`-only call sites (CI workflows, runbooks, CLAUDE.md's own example
commands). These get updated in the same change that lands the script
rewrite, rather than carrying a permanent two-value-enum compatibility path
in 4 scripts indefinitely.

**Not built here** — per wayfinder's plan-don't-do default (no Notes
override on this map), this ticket records the decision; updating the 4
scripts and their call sites is implementation work for whoever executes
this map's destination, not part of charting it.

## Implementation (landed on `claude/snowflake-env-generator`)

**It was five scripts, not four.** This ticket's grilling found its list by
grepping for scripts that *declare* the enum, which missed a transitive
callee: `bootstrap-prod-mdm.sh` invokes `bootstrap-aws-mdm-secrets.sh`
unconditionally with `--env "$ENVIRONMENT"`, and that script enforces the same
`dev|prod` guard. Renaming the caller without the callee would have shipped a
chain that fails at runtime for every new slug, so it is included here — a
correctness requirement of a script this ticket does name, not a scope
expansion.

Renamed to `--env-name <slug>` (positional `<env-name>` for `create-deployer.sh`):
`go-live.sh`, `deploy-snowflake-stack.sh`, `bootstrap-prod-mdm.sh`,
`bootstrap-aws-mdm-secrets.sh`, `create-deployer.sh`.

**Deliberately left on `--env`:** `deploy-aws-application.sh` and
`run-aws-mdm-e2e.sh` (AWS-side, ruled out of scope by the map; ticket 04
already records their enum as the deferred gap), and
`remove-aws-mdm-rds-after-cutover.sh` (dead — MDM moved off AWS RDS entirely).
`go-live.sh` therefore threads **one** identifier to **two** flag names:
`--env-name` to the Snowflake-side delegates, `--env` to the AWS-side ones.
For `prod` that is byte-identical to today's behaviour; for a new slug it is
correct once the AWS side exists under the same slug, which is exactly ticket
04's precondition contract. Pinned by
`test_snowflake_delegates_get_env_name_and_aws_delegates_keep_env`.

Four things implementation forced that the grilling didn't cover:

1. **The "validate the Terraform directory exists" check can't be one shared
   predicate.** `deploy-snowflake-stack.sh` reads *three* roots, and only two
   are what ticket 01's generator emits — the third,
   `access/aws/accounts/<slug>`, is the AWS-side precondition. Each is now
   checked separately and named in its own error, so a missing AWS root says so
   and points at ticket 04 rather than dying opaquely inside Terraform. Worth
   recording that the in-scope/out-of-scope split is not as clean as the map's
   prose implies: an in-scope script hard-depends on an out-of-scope root.
2. **`go-live.sh`'s wizard is the one command allowed to start without the
   flags**, since it collects them interactively. The slug check is a function
   (`validate_env_slug`) called both at parse time and after the wizard's
   prompt — otherwise an empty answer flowed straight into
   `RESOURCE_PREFIX`/`SNOWFLAKE_DATABASE` as `edgartools-` / `EDGARTOOLS_`.
3. **The wizard's environment prompt changed from a `dev|prod` pick-list to
   free text**, which is what a free-form slug requires.
4. **A real latent bug, found by a new test rather than by inspection.**
   `go-live.sh`'s `refresh_config` built `SNOWFLAKE_DATABASE` by uppercasing the
   environment name, so slug `eu-prod` produced `EDGARTOOLS_EU-PROD` — an
   invalid unquoted Snowflake identifier. Same hyphen problem ticket 01 solved
   in the generator, unfixed in this script. Now maps hyphens to underscores
   identically (`EDGARTOOLS_EU_PROD`); a no-op for `prod`, verified.

Call sites updated in the same change: `tests/architecture/test_go_live_wizard.py`
(the pre-existing suite encoded the old contract and caught every missed
rewiring — 14 failures before, plus 6 new tests pinning the new contract),
`scripts/ops/preflight.sh`'s remediation message, and the command examples in
`CLAUDE.md`, `AGENTS.md`, `docs/runbook.md`, `infra/terraform/snowflake/README.md`,
`infra/snowflake/sql/README.md`, `edgar/ai/skills/platform/pipeline-setup.md`.
CLAUDE.md's *historical* 5-whys narratives still say `--env dev`; those are
records of what was true at the time and were left alone deliberately.

Verified: all 5 scripts pass `bash -n`; each guard exercised directly (missing
flag, malformed slug, missing connection, each of the three roots); the `prod`
code path confirmed unchanged; 382 architecture tests pass.
