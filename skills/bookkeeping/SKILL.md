---
name: bookkeeping
description: Plan, validate or deploy Bookkeeping for a specified source and feed in edgartools-platform. Use for pipeline worklists, leases, checkpoints, verified completion and recovery; source mapping and merge-policy design belong to Rules.
---

# Bookkeeping

Use the shared engine in `edgar_warehouse/bookkeeping/clean/`. It retains
control references and evidence; source records stay in their owning stores.
The protocol and supported boundaries are in
[the specification](../../docs/specs/configured-bookkeeping.md).
Run commands from the repository root with `uv run --extra mdm --extra s3`.
Resolve the skill's physical path for its relative references, and verify the
execution checkout contains the fresh engine; another worktree may be older.

## Invocation and required inputs

```text
$bookkeeping plan --source <source> --feed <feed>
$bookkeeping validate --source <source> --feed <feed>
$bookkeeping deploy --source <source> --feed <feed>
```

These are **skill arguments**, not warehouse CLI commands. Every mode requires
both source and feed. Preserve values already provided in the conversation;
ask for any missing mode, source or feed before dependent work. Additional
inputs are a target/stage range, environment, bounded input references and,
for continuation, a run id. Infer those when the request or retained evidence
settles them; ask only when the choice changes the intended work.

Resolve `source` to an existing Rules document, accepting a provider name only
when the repository identifies its source document unambiguously. Resolve
`feed` from source-owned descriptors: the bronze/contract family, publication
family, native member or registered dataset code. For example,
`--source sec.submissions.company --feed submissions` resolves that source's
submissions family; `--source gleif --feed level1` selects its native level1
member and `gleif.level1.v1` dataset. A family containing several datasets
must name the exact included members in the plan. Ambiguous or unknown feeds
require clarification; a feed is neither a Bookkeeping target nor a guessed
alias. Read documents through `edgar_warehouse.rules.files`.

Resolve the binding deterministically before every mode:

```bash
uv run --extra mdm --extra s3 skills/bookkeeping/scripts/resolve_feed.py \
  --source <source> --feed <feed>
```

This read-only helper returns the Rules digest, exact dataset/member set and
available targets. It does not validate input membership or authorize a run;
verify those against captured source manifests in the chosen mode.

Keep source, feed, resolved document/datasets and target in the plan and
validation evidence. Bind the selected feed in frozen worklist control keys
and verify input artifacts belong to those datasets/publications. The runtime
uses `--source <resolved-rules-name>` and `--target`; it has no `--feed` flag.
Recover a run only after its retained manifest proves the same source/feed.

Confirm live commands with `edgar-warehouse bookkeeping --help` and
`edgar-warehouse rules run --help` under the `uv run` prefix. Read
`edgar_warehouse/bookkeeping/clean/cli.py` for runtime bindings. Current
operations are `artifact.copy`, `mdm.ingest`, `mdm.merge` and `mdm.publish`.
Artifact copying uses available bytes, not a provider fetch or parser. Export
and graph use offline contract sinks; hosted adapters and full legacy caller
migration remain unfinished. Report unsupported capabilities as gaps rather
than substituting a legacy run.

## Plan mode

Read the selected feed's captured manifests, existing stage code and control
configuration. Preserve source mapping/policy and stage order. Prepare the
intended `bookkeeping` section and a version 2 manifest: every configured step
has a separate bounded worklist, exact URI/lowercase SHA-256 references, and
predecessor selectors naming declared prerequisite step/key identities.
Source records stay in artifacts. Lease scopes name actual conflicting work
or write resources; a feed label alone does not prove the right conflict scope.

Write a reviewable plan bundle in the current workstream: source/feed binding,
resolved datasets, target, proposed Rules body/digest, manifest/reference and
hash, expected counts per stage, processing versions, lease/check declarations,
publication/delivery requirements, retry/resume behavior and capability gaps.
For continuation, reference the original frozen bundle instead of changing it.
Use captured files and read-only inspection; planning does not activate Rules,
submit work or deploy infrastructure. Done means the full requested scope is
accounted for, including explicit blockers, rather than a claimed executable
plan with unsupported stages omitted.

## Validate mode

Load the plan for the same source/feed. If missing, prepare it through plan
mode first. Pin its hash and validate the exact proposed Rules/configuration,
worklist scope and input hashes with the implementation validators. A later
configuration, input or processing-version change invalidates this validation.

Use bounded captured inputs and isolated PostgreSQL 16 control/destination
stores for actual execution. Verify the selected feed's stage outputs,
accounting, receipts, required publication and journal delivery. Exercise
interruption/resume, lost acknowledgement, duplicate delivery, prerequisite
holes and stale-worker rejection appropriate to the changed stages. Run the
configured contract tests and mandatory
`tests/integration/test_configured_bookkeeping_postgres.py`; prerequisite
failures are failures, not qualifying skips. A generic suite alone does not
prove the selected source/feed worked.

Produce validation evidence containing the source/feed binding, plan/config/
manifest hashes, processing versions, sample bounds, actual run/receipt
references, expected/verified counts, check/delivery results and remaining gaps.
Only mark the requested scope passed when its required work and verification
were exercised successfully. Partial validation stays explicit and cannot
qualify the omitted stages for deployment. Validation executes isolated samples;
it does not activate live Rules, publish to live destinations or perform AWS
cutover. This is Bookkeeping validation, not the unfinished Rules Batch Gate
evaluator, and does not grant a person's MDM approval.

## Deploy mode

Read [DEPLOY.md](DEPLOY.md). Apply the validated configuration and submit or
resume its bounded run in the selected environment. Verify that the plan,
validation evidence and frozen inputs still match the requested source/feed.
Deploy mode uses the existing Rules lifecycle and Bookkeeping runner; it does
not introduce a new command, store or source callback. Unsupported scope stays
blocked. Infrastructure rollout belongs here only when explicitly included
in the user's deployment request and independently qualified.

## Result

Report mode, source, feed, resolved target, bundle/run references, commands,
verification and concrete remaining gaps. Record unsupported commands and
operational assumptions in the current workstream's log. Never present a plan
as validation, or isolated validation as completed live deployment.
