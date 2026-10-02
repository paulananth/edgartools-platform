---
name: bookkeeping
description: Initialize or migrate Bookkeeping, or plan, validate, run, inspect and recover work through loader-independent control. Enforce separation of worklists, leases, checkpoints and verified evidence from external workload execution and destination verification. Source interpretation belongs outside Bookkeeping.
---

# Bookkeeping

**Modes:** init, migrate, plan, validate, run, status, recover. Bookkeeping
owns work control and verified completion. External workers own feed execution
into silver and MDM. Running mastering (the Merge
Stage) is the `mdm` target of **run**. Its command is `edgar-warehouse rules
run --target mdm`, which submits the approved versions to this Bookkeeping
runner. There is no `bookkeeping run` command (operator, 2026-10-02: "Keep
`rules run`"). Plan, validate and recover are steps you follow with the
existing commands; they are not commands of their own.

## Required independence

Bookkeeping must operate without any loader or domain implementation installed.
Its control process, CLI construction and helpers must not import, instantiate
or call loaders, parsers, Silver/MDM implementations or source-specific
execute/reconcile/verify callbacks. Passing the whole Bookkeeping object to an
external operation also violates this requirement. Moving a callback to another
file or selecting its name in YAML does not remove the dependency.

Use a fixed task protocol with immutable specifications and references. External
workers execute and reconcile effects; external verifiers check destinations.
Bookkeeping owns dependencies, leases/fencing, retries, checkpoints, evidence
admission and control outbox delivery. Source/feed names are opaque selection
metadata; source grammar and domain checks stay outside control.

Read [INDEPENDENCE.md](INDEPENDENCE.md) before planning or changing an execution
path, validating its architecture, or running/recovering it under this contract.
It defines the evidence required to claim independence and the current runtime
gap. Keep that gap explicit; do not route through Company callbacks as a fallback.

**Use another skill when:**
- a feed is new: use **data-onboarding**;
- a live feed's mapping, quality or matching rules change: use
  **refining-rules**;
- recording or recovering journal delivery: use **change-journal**.

Use the shared engine in `edgar_warehouse/bookkeeping/clean/`. It retains
control references and evidence; source records stay in their owning stores.
The currently implemented protocol and supported boundaries are in
[the specification](../../docs/specs/configured-bookkeeping.md).
The required replacement design is linked from INDEPENDENCE.md; it is proposed,
not implemented. Existing CLI syntax is not proof of loader independence.
Run commands from the repository root with `uv run --extra mdm --extra s3`.
Resolve the skill's physical path for its relative references, and verify the
execution checkout contains the fresh engine; another worktree may be older.

## Invocation and required inputs

```text
$bookkeeping plan --source <source> --feed <feed>
$bookkeeping validate --source <source> --feed <feed>
$bookkeeping run --source <source> --feed <feed>
$bookkeeping status <run-id>
$bookkeeping recover <run-id>
$bookkeeping init
$bookkeeping migrate
```

These are **skill arguments**, not warehouse CLI commands. Plan, validate and
run require both source and feed. Init and migrate operate on the whole
fresh control store, so they do not take source or feed. Preserve values already
provided in the conversation; ask for missing source or feed only when a
feed-scoped mode needs them. Additional inputs are a target/stage range,
environment, bounded input references and,
for continuation, a run id. Infer those when the request or retained evidence
settles them; ask only when the choice changes the intended work.

Resolve `source` to an existing Rules document, accepting a provider name only
when the repository identifies its source document unambiguously. Resolve
`feed` only from an active `acquisition.feeds` declaration. The sole active
acquisition binding is `--source sec.submissions.company --feed submissions`.
GLEIF retains MDM contracts but has no active acquisition feed. Read documents
through `edgar_warehouse.rules.files`.

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
`edgar_warehouse/bookkeeping/clean/cli.py` for runtime bindings. The current
coupled runtime registers source/domain operations; these are gap evidence,
not the required architecture. Current
Company operations are `provider.capture`, `company.expand`, `source.evidence`,
`company.silver`, `company.prepare`, `mdm.ingest`, `company.publish_expand`, and
`mdm.publish`. The existing coupled path can prepare a bounded Company scope
without requesting SEC or starting a run. Pin ticker, Name Census, reviewed bindings and a timezone-aware
`as_of` in the support manifest:

```bash
uv run --extra mdm --extra s3 edgar-warehouse bookkeeping prepare \
  --source sec.submissions.company --feed submissions \
  --scope-manifest <URI> --scope-sha256 <SHA256> \
  --support-manifest <URI> --support-sha256 <SHA256> --output-root <file-URI>
```

Its existing submission command is `rules run --source
sec.submissions.company --feed submissions --target company`. Generated page,
ingest, and publication work joins its parent completion in the same root run.
Local file evidence qualifies the Company bundle; AWS feeds remain disabled.

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

Audit the control dependency path first using INDEPENDENCE.md. Plan external
worker/verifier profiles and frozen specification references; do not add a
source-specific capability to the control registry to fill an execution gap.
Record missing task-protocol support as required implementation work.

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

Validate loader independence separately from source output correctness using
INDEPENDENCE.md. A successful feed run through the current Company callbacks
does not qualify a loader-independent controller.

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
qualify the omitted stages for a run. Validation executes isolated samples;
it does not activate live Rules, publish to live destinations or perform AWS
cutover. This is Bookkeeping validation, not the unfinished Rules Batch Gate
evaluator, and does not grant a person's MDM approval.

## Run mode

(Named "deploy" before 2026-09-30.) Read [RUN.md](RUN.md). Apply the validated configuration and submit or
resume its bounded run in the selected environment. Verify that the plan,
validation evidence and frozen inputs still match the requested source/feed.
Use the existing Rules lifecycle for approval and frozen configuration; execute
through a qualified loader-independent task path. The current coupled runner
does not meet that requirement. Until the replacement exists, report execution
as unsupported under this contract and continue independent inspection or
planning. Do not invent a command or silently use source callbacks.
Infrastructure rollout belongs here only when explicitly included in the user's
run request and independently qualified.

## Status mode

```bash
uv run --extra mdm --extra s3 edgar-warehouse bookkeeping runs --limit 20
uv run --extra mdm --extra s3 edgar-warehouse bookkeeping status <run-id> --limit 100
uv run --extra mdm --extra s3 edgar-warehouse bookkeeping checks <run-id>
uv run --extra mdm --extra s3 edgar-warehouse bookkeeping leases <run-id> --limit 100
```

Each needs `BOOKKEEPING_CLEAN_DATABASE_URL` (the runtime login). `status`,
`checks` and `leases` take the run id; `runs` lists them.

## Recover mode

Read [RECOVERY.md](RECOVERY.md). Resume a run with
`edgar-warehouse bookkeeping resume <run-id>` (exit 3 means the run is not
complete yet). Delivery to the Journal of a run's committed events is the
Change Journal skill's **recover-delivery**.

Those resume commands describe the current implementation. Establish its
dependency boundary before claiming it meets this skill's independence contract.

## Result

Report mode, source, feed, resolved target, bundle/run references, commands,
verification and concrete remaining gaps. Record unsupported commands and
operational assumptions in the current workstream's log. Never present a plan
as validation, or isolated validation as a completed live run.
