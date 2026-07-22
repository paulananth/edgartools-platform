# 01 — Does the completed prodb→prod cutover leave runtime_access roles still shared?

Type: research
Status: open
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

(resolved on close: what the live IAM/Terraform state actually shows, and
whether the module still needs the coordinated rename fix TODOS.md
originally described)
