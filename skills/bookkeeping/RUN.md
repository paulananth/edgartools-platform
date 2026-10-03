# Run the validated source and feed

First read [INDEPENDENCE.md](INDEPENDENCE.md). `rules run` only submits; the
work is done by workers in their own processes, checked by separate verifiers,
and finished by `bookkeeping finalize`. A step whose worker profile has no
worker yet (Company, Person and MDM until mastering to-do 20c–20e) is a
blocker to report, never a reason to run it some other way.

Load the source/feed plan and validation evidence. Check their hashes against
the intended Rules body, processing versions and frozen manifest; resolve every
declared feed member. Confirm the requested environment, target and bound.
Use existing authorization for the run scope. Missing validation or an
unsupported required stage is a blocker, not a reason to drop that stage.

## Configuration and execution

Supply connection URLs through the environment without printing credentials:
`BOOKKEEPING_CLEAN_DATABASE_URL`, `RULES_DATABASE_URL`,
`BOOKKEEPING_MANIFEST_ROOT` and `CHANGE_JOURNAL_DATABASE_URL`; MDM work also needs
`MDM_DATABASE_URL`. Activation/registration connections and provisioning are
described in [the specification](../../docs/specs/configured-bookkeeping.md).
Legacy `BOOKKEEPING_DATABASE_URL` and old run ids are not fallbacks.

For a new or changed Rules body, write only the planned configuration through
`edgar_warehouse.rules.files`, save a new version, and record the evaluator's
real exact-digest proof with `rules record-proof`. That command records proof;
it does not evaluate a Batch Gate. MDM configurations require the person's
approval of that exact version, recorded through the Data Onboarding skill's Approve
steps in their name and words. Honor an approval already given for that
version; when absent, explain the Rules governance requirement and wait for
the person's approval. Activate through the existing Rules lifecycle.
Source documents own MDM dataset registration; platform-owned MDM contracts
still lack handoff support. An existing approved active version can be reused
when its exact content matches the validated plan.

Submit the selected source/feed's manifest, then run each step's worker and
verifier, in step order, and finish the run:

```bash
edgar-warehouse rules run \
  --source "$RULES_SOURCE_NAME" --feed "$SOURCE_FEED" --target "$BOOKKEEPING_TARGET" \
  --input-manifest "$INPUT_MANIFEST_URI" --input-sha256 "$INPUT_MANIFEST_SHA256"
edgar-warehouse workers work <profile> "$RUN_ID" --limit 100
edgar-warehouse workers verify <profile> "$RUN_ID" \
  --reports "$REPORT_ROOT_URI" --limit 100
edgar-warehouse bookkeeping finalize "$RUN_ID"
```

Feed is bound by the validated frozen worklist, source-input dataset/
publication identities and the explicit Rules runner `--feed` option. Keep the durable run
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
and verifiers again. Keep the run id, original Rules reading, pinned worker
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
