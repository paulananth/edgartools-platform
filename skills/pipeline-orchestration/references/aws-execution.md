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

## What the old state machines taught

Each is a rule now; the evidence is the old pipeline's deployed definitions.

| Rule | Why |
|---|---|
| One generic state machine; the data's own configuration (the chain file) names the work, and the definition names no step, lane or source | Many machines, each built by hand, drifted: shared stages were copied into several machines and changed apart, and many machines never ran |
| Every Task has `TimeoutSeconds` and `HeartbeatSeconds` | The language sets no timeout by default: a lost task waits forever |
| Retries live in one place: the worker's own attempts. The state machine retries nothing, or only a dead worker (`States.HeartbeatTimeout`), once | A state-machine `Retry` on `States.TaskFailed` around a command that retries multiplies the attempts |
| The task contract is the same locally and on AWS: an activity task here, an ECS `runTask.sync` there, the same input and the same command | Only the `Resource` changes, so the local run proves the definition |
| The image is pinned by commit, and the gate checks the running code is that commit | A machine left on an old image gave a false positive |
| Parallel work stays bounded inside the worker (its bundles, its workers); the machine runs only independent units in parallel | Many concurrent copies of one stage collided on the same files |
| A failure in one parallel branch is caught there, so the others go on; the execution fails at the end | An inline `Map` stops every branch when one fails |

## Step Functions Local

AWS calls it unsupported, with no feature parity: a local pass proves the definition's shape on this machine, never AWS
behaviour (check that with the TestState API or on AWS). Measured on it:

- A `Map` with a concurrency of one still started the next item after a failed one: run steps that must stop at the first
  failure as a Choice loop, not a `Map`.
- boto3 reads its address from `AWS_ENDPOINT_URL_SFN` (the service's id), never `AWS_ENDPOINT_URL_STEPFUNCTIONS`; a
  wrong name sends the client to real AWS with the placeholder login. A test asserts the client's `endpoint_url`.
- A long poll still held by a worker that was replaced takes the next task and loses it: the task times out on its
  heartbeat. Make a new activity for each execution and delete the older ones, after checking nothing runs.
- `docker compose up` of one service reads every service's variables: set each the file requires before the first `up`.

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
