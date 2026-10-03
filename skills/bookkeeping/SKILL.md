---
name: bookkeeping
description: Initialize or migrate Bookkeeping, or plan, validate, run, inspect and recover work through loader-independent control and its worker task protocol. Enforce separation of worklists, leases, checkpoints and verified evidence from external workload execution and destination verification. Source interpretation belongs outside Bookkeeping.
---

# Bookkeeping

**Modes:** init, migrate, plan, validate, run, status, recover. Bookkeeping
owns work control and verified completion. Workers, each in its own process,
own the work itself. `edgar-warehouse rules run` submits the approved versions;
workers then pull the work (`python -m edgar_warehouse.workers work`), separate
verifiers check it (`… verify`), and `edgar-warehouse bookkeeping finalize`
delivers control's events and records the run's checks. There is no
`bookkeeping run` command (operator, 2026-10-02: "Keep `rules run`"). Plan,
validate and recover are steps you follow with the existing commands; they are
not commands of their own.

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
It defines the evidence required to claim independence and what is built so
far. The callbacks are gone (mastering to-do 20a); never add one back.

**Use another skill when:**
- a feed is new: use **data-onboarding**;
- a live feed's mapping, quality or matching rules change: use
  **refining-rules**;
- recording or recovering journal delivery: use **change-journal**.

Use the shared engine in `edgar_warehouse/bookkeeping/clean/`. It retains
control references and evidence; source records stay in their owning stores.
The currently implemented protocol and supported boundaries are in
[the specification](../../docs/specs/configured-bookkeeping.md).
The design is linked from INDEPENDENCE.md; its status there says which gates
have run. Existing CLI syntax is not proof of loader independence.
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
`edgar-warehouse rules run --help` under the `uv run` prefix.

### The task protocol

A step's `operation` names the **worker profile** that pulls it. Workers and
verifiers reach Bookkeeping only through these commands, which print JSON:

| Command | Who calls it | What it does |
|---|---|---|
| `bookkeeping claim <run> --profile P --limit N` | worker | Claims units and prints task envelopes |
| `bookkeeping renew --envelope -` | worker, verifier | Renews the lease while the work runs |
| `bookkeeping report --envelope - --candidate URI --sha256 H --runtime D` | worker | Reports the candidate; the first report pins the profile's runtime for the run |
| `bookkeeping verifications <run> --profile P` | verifier | Lists reported candidates whose lease is live |
| `bookkeeping admit --verification - --report URI --sha256 H` | verifier | Admits a report bound to that work, with every check the step names; completes the unit |
| `bookkeeping fail --envelope - --message M` | worker, verifier | Gives the attempt up; the unit waits |
| `bookkeeping finalize <run>` | operator | Delivers control's events and records the run's checks |
| `bookkeeping grant-profile --profile P --worker W --verifier V` | operator (migration owner) | Lets login W report profile P's work and a different login V verify it |

Workers and verifiers connect as their own logins, each a member of the
runtime role. A profile no login was granted cannot report or verify anything.
Control is also packaged alone: `packages/bookkeeping` (`edgar-bookkeeping`).

`python -m edgar_warehouse.workers work|verify <profile> <run>` runs a worker
or a verifier. The profiles built so far are `artifact.copy` and `jsonl.count`.
Company, Person and MDM have no worker yet: SEC Company and acquisition arrive
in mastering to-do 20c, Person in 20d, MDM in 20e. Until then, report their
execution as unsupported; never route them through an in-process callback.

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
INDEPENDENCE.md. A worker's own success never qualifies the run: only its
verifier's admitted report does.

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
Use the existing Rules lifecycle for approval and frozen configuration. Submit
with `rules run`, then run each step's worker and verifier and finish with
`bookkeeping finalize` (see RUN.md). A step whose profile has no worker yet is
unsupported: report it, and do not invent a command.
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

Read [RECOVERY.md](RECOVERY.md). `edgar-warehouse bookkeeping resume <run-id>`
rechecks every completed unit's evidence and reopens the run (exit 3 means it
is not complete yet); then run the workers and verifiers again. A worker
reconciles an earlier attempt's effect before writing. Delivery to the Journal
of a run's committed events is the Change Journal skill's **recover-delivery**.

## Result

Report mode, source, feed, resolved target, bundle/run references, commands,
verification and concrete remaining gaps. Record unsupported commands and
operational assumptions in the current workstream's log. Never present a plan
as validation, or isolated validation as a completed live run.
