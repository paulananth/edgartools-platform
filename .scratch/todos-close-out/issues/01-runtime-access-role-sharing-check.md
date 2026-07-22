# 01 — Does the completed prodb→prod cutover leave runtime_access roles still shared?

Type: research
Status: resolved
Blocked by: (none)

## Question

TODOS.md's "runtime_access module: shared, non-namespaced IAM roles across
dev/prod" entry was marked RESOLVED as a side effect of the account
migration + `prodb` build (confirmed live 2026-07-17), but explicitly
flagged: "re-verify if the `prodb`→`prod` promotion ... ever consolidates
role naming back down to one shared set."

That promotion has since executed in full (TODOS.md: "RESOLVED
(2026-07-19): prodb→prod promotion executed in full — no prodb resources
remain in the serving path") — the trigger condition for the re-verify has
already fired, and nobody has re-checked it since.

Re-verify now: after the 2026-07-19 cutover, do
`sec_platform_runner_execution`/`_task`/`_step_functions` (or their
now-current equivalents, e.g. `sec_platform_prod_runner_*` per the cutover
notes) still share literal IAM role ARNs between dev and prod, or did the
cutover's renaming (`sec_platform_prod_runner_*`) incidentally namespace
them? Check live AWS IAM (`aws iam get-role`, ECS task definitions'
`executionRoleArn`/`taskRoleArn` for dev vs prod) and
`infra/terraform/access/aws/modules/runtime_access/main.tf` against current
reality, not the TODOS.md narrative, which may now be stale either way.

## Answer

**Dev and prod no longer share these IAM roles** — the 2026-07-19 cutover
permanently namespaced them apart. Confirmed live: `edgartools-dev-large`'s
task def uses `sec_platform_runner_execution`/`_task` (unnamespaced);
`edgartools-prod-large`'s uses `sec_platform_prod_runner_execution`/`_task`
(namespaced). Distinct ARNs, no sharing.

Root cause of the separation: `infra/terraform/access/aws/accounts/prod/main.tf`
now explicitly sets `runner_role_name_prefix = "sec_platform_prod"`, while
dev's account root doesn't override it (still gets the module's default
`"sec_platform"`). The module itself
(`infra/terraform/access/aws/modules/runtime_access/main.tf:17-19`) was
**never fixed** to namespace by `name_prefix` — the separation is accidental
(one account root remembered to override the prefix), not structural.

**Disposition:** TODOS.md's re-verify flag can be closed — the prodb→prod
promotion did not collapse the naming back to a shared set. But the
underlying module-level gap is still real: any future environment reusing
this module without an explicit `runner_role_name_prefix` override will
collide with dev again. Worth a follow-up TODOS.md note (not urgent, no
live incident) rather than a new close-out ticket.
