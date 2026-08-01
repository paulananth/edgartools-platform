# Implement run-scoped Daily Identity Refresh publication

Type: task
Status: claimed
Blocked by: 58

## Question

Implement the approved run-scoped Daily Identity Refresh architecture without
weakening canonical silver integrity, then produce the immutable-image
full-chain timing evidence required before schedule activation.

## Approved contract

- Fetch and persist exactly one run-bound global ticker/reference snapshot
  before CIK batching.
- Persist one immutable, checksummed company-identity delta per declared CIK
  batch; batches do not publish canonical silver.
- Persist a run manifest binding selected CIK universe, image identity,
  reference snapshot, ordered batch declarations, checksums, and outcomes.
- Run one reducer only after the manifest is complete and successful. It must
  merge in manifest order, preserve current fail-closed semantic merge rules,
  and make one immutable-staging, ETag-guarded canonical promotion.
- Retry only failed batches under the unchanged run contract. For an
  interrupted or ETag-conflicted reducer, retry only the reducer with bounded
  attempts, rehydrating canonical and re-merging unchanged verified inputs.
- Emit operator-readable run, batch, reducer, checksum, baseline/result ETag,
  merge-order, and canonical-promotion-count evidence.

## Acceptance

- Unit and workflow tests prove no partial manifest can publish, successful
  deltas are not recomputed during a failed-batch retry, reducer retries never
  rerun batches, and ambiguous merge conflicts fail closed.
- Non-daily `bootstrap-fundamentals --mode company-identity` behavior remains
  compatible.
- A new production full-chain run is bound to the immutable warehouse image
  and proves complete batch coverage, exactly one canonical publication, and
  elapsed time at or below six hours.
- The recurring schedule remains disabled until the evidence is reviewed and
  explicit AWS Operator GO is recorded.

## Progress (2026-08-01)

Local implementation is complete and verified:

- `compute-identity-refresh-window` now writes an immutable run plan and the
  one run-bound reference snapshot instead of publishing canonical silver.
- Scheduled `company-identity` batches receive the same run id, skip global
  reference refresh, and write immutable checksummed deltas plus outcomes.
- `reduce-identity-refresh` validates the plan/outcomes/image binding,
  rechecks each checksum, merges inputs in declared order under the existing
  fail-closed merge rules, and performs one staged ETag-guarded promotion.
  Its bounded retry is reducer-only; the state-machine fan-in never returns
  to the batch Map.
- Focused unit, application, and state-machine tests pass (106 tests), as
  does an actual local DuckDB reducer merge/promotion. Normal non-daily
  `bootstrap-fundamentals --mode company-identity` compatibility is covered
  by the application suite.

Remaining: publish/deploy an immutable warehouse image, execute one new prod
full-chain run, and record direct evidence of full batch coverage, exactly one
canonical promotion, and elapsed time no greater than six hours. The recurring
schedule remains disabled pending that reviewed evidence and explicit AWS
Operator GO.

## Production-readiness update (2026-08-01)

- The focused Daily Identity Refresh suites pass locally: 138 tests covering
  the reducer contract, bounded-window behavior, lease behavior, and generated
  state-machine/schedule definitions. `git diff --check` also passes.
- Immutable warehouse image:
  `690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-warehouse@sha256:70cdc1c710d1a334a28e7c894f41db61a024baf61a3ddaa76029a937b2ea5e57`
  (published as `operator-identity-refresh-20260801T115921Z`). Live ECS
  medium revision 104 uses that exact digest.
- Live `edgartools-prod-daily-incremental` definition contains the reducer
  fan-in after the bounded company-identity Map; both use medium revision 104
  and pass the execution name as the immutable run identity. EventBridge daily
  rules remain absent/disabled.
- A new full-chain execution was intentionally not started because the old
  `daily-post-txt-fix-20260801T005633Z` execution is still RUNNING, holds the
  single refresh lease, and is retrying an old `edgartools-prod-large:94`
  task. Starting another execution now would only produce the designed
  `deferred` result. Do not stop the old execution without explicit operator
  direction.

## Full-chain execution started (2026-08-01)

With explicit operator approval, the superseded old execution was aborted and
its exact held lease was released by a successful (`exit 0`) deployed
`release-identity-refresh-lease --run-id daily-post-txt-fix-20260801T005633Z`
task. The fresh manual execution is now RUNNING:

- execution: `daily-run-scoped-identity-20260801T121338Z`
- ARN:
  `arn:aws:states:us-east-1:690839588395:execution:edgartools-prod-daily-incremental:daily-run-scoped-identity-20260801T121338Z`
- input: `{}`
- warehouse image: `sha256:70cdc1c710d1a334a28e7c894f41db61a024baf61a3ddaa76029a937b2ea5e57`

This is the acceptance run. Record batch coverage, reducer evidence, one
canonical promotion, and elapsed time only after its terminal outcome.
