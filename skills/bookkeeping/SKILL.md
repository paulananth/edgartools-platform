---
name: bookkeeping
description: Initialize or migrate the fresh Bookkeeping store, or plan, validate and deploy work for a specified source and feed in edgartools-platform. Worklists, leases, checkpoints and recovery belong here; source policy belongs to Rules.
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
$bookkeeping init
$bookkeeping migrate
```

These are **skill arguments**, not warehouse CLI commands. Plan, validate and
deploy require both source and feed. Init and migrate operate on the whole
fresh control store, so they do not take source or feed. Preserve values already
provided in the conversation; ask for missing source or feed only when a
feed-scoped mode needs them. Additional inputs are a target/stage range,
environment, bounded input references and,
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

Resolve the binding deterministically before every feed-scoped mode:

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
uses `--source <resolved-rules-name>`, `--target` and an explicit `--feed`
binding on Rules submission for acquisition documents.
Recover a run only after its retained manifest proves the same source/feed.

Confirm live commands with `edgar-warehouse bookkeeping --help` and
`edgar-warehouse rules run --help` under the `uv run` prefix. Read
`edgar_warehouse/bookkeeping/clean/cli.py` for runtime bindings. Current
operations are `artifact.copy`, `provider.capture`, `source.evidence`,
`mdm.ingest`, `mdm.merge` and `mdm.publish`.
Artifact copying uses available bytes, not a provider fetch or parser. Export
and graph use offline contract sinks; hosted adapters and full legacy caller
migration remain unfinished. Report unsupported capabilities as gaps rather
than substituting a legacy run.

## Init and migrate modes

Use `init` for an empty `bookkeeping_clean` PostgreSQL 16 database; use
`migrate` only for an already initialized, checksummed Bookkeeping schema.
Both apply pending numbered migrations and refresh restricted runtime grants.
`migrate` refuses to create a missing schema; checksum drift or an untracked
schema blocks both. These modes create no run, import no legacy history or
checkpoints, and do not change Rules, Change Journal or destination schemas.

Use a separate migration owner in `BOOKKEEPING_CLEAN_MIGRATION_DATABASE_URL`
and an existing restricted runtime role. Never use the legacy
`BOOKKEEPING_DATABASE_URL` or a runtime login as the migration owner. Check
the exact database, PostgreSQL version and role before executing; do not print
connection secrets. Then run the selected command and verify the returned
migration checksums, five control tables, runtime privileges and zero imported
run/work rows:

```bash
uv run --extra mdm --extra s3 edgar-warehouse bookkeeping init --runtime-role <role>
uv run --extra mdm --extra s3 edgar-warehouse bookkeeping migrate --runtime-role <role>
```

Select one command for the requested state. If destination transaction guards
are in scope, provision them separately with `bookkeeping init-guard` using
`DESTINATION_MIGRATION_DATABASE_URL` and its restricted destination role.
Neither control-store mode silently provisions a destination or executes work.

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
