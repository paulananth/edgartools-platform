# Run the validated source and feed

First read [INDEPENDENCE.md](INDEPENDENCE.md). `rules run` only submits; the
work is done by workers in their own processes, each checking its own result,
and finished by `bookkeeping finalize`. A step whose worker profile has no
worker yet (no key in `PROFILES`, `edgar_warehouse/workers/__init__.py`) is a
blocker to report, never a reason to run it some other way.

For one source's target over a captured delivery, `edgar-warehouse load` does
every step below in one command and is safe to rerun
([data-operations, Load a capture](../data-operations/SKILL.md#load-a-capture)).
The steps here are what it runs, for diagnosing a run by hand.

Load the source/feed plan and validation evidence. Check their hashes against
the intended Rules body, processing versions and frozen manifest; resolve every
declared feed member. Confirm the requested environment, target and bound.
Use existing authorization for the run scope. Missing validation or an
unsupported required stage is a blocker, not a reason to drop that stage.

## Configuration and execution

Select the environment, the worker duty, manifest storage and any
registration connections through
[Connection URLs and environment](../data-platform/SKILL.md#connection-urls-and-environment).
Provisioning does not authorize execution.
Old run ids are not fallbacks.

A new or changed rules file is checked with `rules check`; the run freezes it ([check and load](../data-onboarding/LOAD.md)).

Submit the selected source/feed's manifest, then run each step's worker,
in step order, and finish the run:

```bash
edgar-warehouse rules run \
  --source "$RULES_SOURCE_NAME" --target "$BOOKKEEPING_TARGET" \
  --input-manifest "$INPUT_MANIFEST_URI" --input-sha256 "$INPUT_MANIFEST_SHA256"
# A live acquisition run adds --feed "$SOURCE_FEED" (it makes provider requests: the operator's permission first).
edgar-warehouse workers work <profile> "$RUN_ID" \
  --reports "$REPORT_ROOT_URI" --limit 100
edgar-warehouse bookkeeping finalize "$RUN_ID"
```

`finalize` delivers every one of the run's Change Journal events, `--limit`
a batch (default 100, at most 1000), then records the run's checks. A crash
part-way is picked up by running it again.

A live acquisition run's feed is bound by the validated frozen worklist,
source-input dataset/publication identities and the Rules runner's `--feed`;
a run over captured files names none. Keep the durable run
id printed on stderr. For explicit platform jobs use their existing
`--pipeline` selection while retaining the source/feed binding in the plan
and inputs; never silently replace a source-owned mapping with a platform job.
Changed configuration, inputs or a worker's runtime require a new run.
Empty success needs explicit configuration and verified manifest evidence.

## Verify or continue

Inspect bounded `bookkeeping status <run-id> --limit 100` and
`bookkeeping leases <run-id> --limit 100`. After a lost submission acknowledgement
use `bookkeeping runs --limit 100`, optionally with `--state`; prove its retained
manifest belongs to the same source/feed before selecting a run. Use
`bookkeeping checks <run-id>` for verification; corrupt frozen scope can make
it mark the run blocked. Listings are bounded; state counts cover all work.

Read [RECOVERY.md](RECOVERY.md) for incomplete runs. Authorized continuation uses
`bookkeeping resume <run-id>`, or the original Rules selection with
`--resume-run-id <run-id>` and no replacement input options, then the workers
again. Keep the run id, original Rules reading, pinned worker
runtimes and business idempotency keys.
Verified effects reconcile before execution. A fresh Rules version or a changed
authoring file is not a substitute for missing original evidence.

The requested run completes only when `run.state` is `complete`,
expected work and required checks passed, and pending journal delivery is zero.
A status command's exit code 0 is not that proof. A bounded Rules run or
Bookkeeping resume can return 3 while more work remains; inspect the returned
state before deciding the recovery action. Exceptions also require inspection.
Report partial progress and the exact recovery action instead of claiming the run
succeeded. AWS cutover, history retirement or schema provisioning occur only
when included in the authorized run scope and qualified separately.
