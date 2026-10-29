# AWS execution and lifecycle

Before AWS inspection or changes, read
[aws-snowflake-operations](../../aws-snowflake-operations/SKILL.md) for current
account, roles and retired targets. Verify deployed revision and existing
machines first. The retired application deployment script is not a supported
workflow builder. Passive Terraform does not deploy runnable workflows/timers;
use an approved committed workload script for that lifecycle. A missing builder
is an implementation gap, not permission for an unrecorded manual rollout.

## Efficient workflow shape

Use a native per-pipeline timer and a small workflow that launches qualified
workers in configured order. Pass immutable artifact references and identifiers,
not records or large intermediate payloads. Reuse existing control for admission,
coalescing, recovery and completion. Avoid a second dispatcher/state service.

For long-running containers, assess Standard Step Functions with the optimized
ECS `runTask.sync` integration. Express has different duration, delivery and
billing semantics and does not support the `.sync` integration pattern. Choose
from the actual worker duration and correctness requirements, rather than the
assumption that Express is cheaper. Container exit success still needs the normal
pipeline verifier. See [workflow types](https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html)
and [ECS integration](https://docs.aws.amazon.com/step-functions/latest/dg/connect-ecs.html).

Keep transitions, payloads and history bounded; batch useful work inside existing
bounded work units rather than one orchestration transition per record. Configure
timeouts and error handling; account for service launch retries separately from
Bookkeeping work retries. An aborted `.sync` workflow only attempts to cancel its
underlying job: confirm actual compute termination and use the supported scoped
stop action if needed. See [integration patterns](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html)
and [best practices](https://docs.aws.amazon.com/step-functions/latest/dg/sfn-best-practices.html).

Check timer timezone, daylight-saving behavior, precision, flexible window,
retry/dead-letter handling and missed-trigger policy against the configured
business schedule. Do not promise second-level timing from a minute-precision
scheduler. See [schedule types](https://docs.aws.amazon.com/scheduler/latest/UserGuide/schedule-types.html).

## Evidence and release

Validate the rendered ASL with the supported definition validator before creating
resources; inspect diagnostics and the returned `result`, not just process exit.
[ASL validation](https://docs.aws.amazon.com/cli/latest/reference/stepfunctions/validate-state-machine-definition.html)
proves syntax, not IAM, data readiness, cancellation, idempotency or a real run.

Before rollout, retain the rendered definition/configuration, selected image,
scoped execution-role/access policy, lifecycle inventory and qualification plan.
Use service-assumed restricted roles and the existing secret-reference mechanism.
Readiness requires the normal worker/verifier and durable-receipt evidence from
an authorized bounded run. Creating these skills does not deploy that run.
