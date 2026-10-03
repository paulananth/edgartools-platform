# Fresh configured Bookkeeping

Current acquisition status (2026-09-29): only
`sec.submissions.company/submissions` is active. The local Company caller and
bounded generated-work migration are described in
[the Company route](../company-only-acquisition.md). Branch names, feed suites,
and test counts below record the earlier implementation state.

Core branch: `codex/configured-bookkeeping` (PR #732). Stage work continues on
`codex/bookkeeping-stage-work`, based on the refreshed core branch. The complete supplied
plan is the objective. **The current implementation does not yet replace every
legacy caller or qualify a production cutover.**

## Implemented boundary

`edgar_warehouse.bookkeeping.clean` uses only
`BOOKKEEPING_CLEAN_DATABASE_URL`, never the old `BOOKKEEPING_DATABASE_URL`.
The PostgreSQL 16 database is `bookkeeping_clean`. Its schema has exactly
five tables: `pipeline_run`, `work_item`, `lease`, `checkpoint`, and
`journal_outbox`. Migration checksums live in a schema comment, so they do
not add a sixth control table. No old history or checkpoints are imported.

Runtime may read the tables and execute bounded control functions. It may
not change tables directly, create schema objects, or compact records.
Migration checks inherited privileges as well as explicit grants. An
independent destination has `bookkeeping_guard.resource`, and the shared
Change Journal has an append-only `journal.event`; neither is another
Bookkeeping root run.

The interface is the task protocol (mastering to-do 20a). `Bookkeeping.start`
freezes a run; workers in their own processes `claim` task envelopes for a
worker profile, `renew` them while they work, and `report` a candidate; a
separate verifier lists `verifications` and has its report admitted with
`admit`. `resume`, `status`, `deliver` and `finalize` complete the set. A step's
`operation` names its worker profile. Control holds no executor, reconciler,
verifier or check callback, and no branch on a source or operation name.

- **Envelope:** run, step, key, attempt and lease proof; the frozen Rules
  reference; the resolved input; the intended output; the step's domain checks;
  and an **effect key**, the digest of the Rules reference, step, key and frozen
  unit, which stays the same across retries of the same work.
- **Report:** a worker's candidate (URI and hash) moves the unit to `reported`.
  The first report of a profile in a run pins that profile's runtime digest
  (`pipeline_run.runtimes`); a different runtime later is refused.
- **Admission:** the verifier's report must name exactly this run, step, key,
  attempt, effect key and candidate, and report every domain check the step
  names, all true. Control itself checks `input.hash` and `output.receipt`
  (the bytes it can read) and the run checks `manifest.hash`, `work.accounting`
  and `journal.delivered`. A database trigger refuses any completion that is
  not the reported candidate, whichever finish function commits it.
- **Issuers (20b):** each profile has a worker role (`bk_worker_<profile>`) and a
  verifier role (`bk_verifier_<profile>`), granted with `bookkeeping
  grant-profile`. Only the worker role reports; only the verifier role verifies
  and completes, and never the login that reported. The verifier names its
  runtime in its report, pinned for the run like the worker's.
- **Package:** `packages/bookkeeping` builds the control alone
  (`edgartools-bookkeeping`, with the `edgartools-change-journal` wheel).
- **Events:** control emits only `work.verified`. Domain events go through the
  worker's own Journal intent.

Workers built so far (`edgar_warehouse/workers`): `artifact.copy` and
`jsonl.count`. The MDM, acquisition, source-evidence and Company capabilities
this section used to list were in-process callbacks and are deleted; they
return as workers in mastering to-do 20c (SEC Company and acquisition), 20d
(Person) and 20e (MDM). Journal delivery uses the shared Change Journal adapter.

## Rules ownership and lifecycle

The operator assigned Codex the required Rules integration during this task,
including schema, resolver and runner. This extends Claude's planned single
`rules.rule_version` table with the `pipeline` document kind. No other
configuration table is created. The implementation lives in the existing
`edgar_warehouse.rules` package; Claude should reuse it when adding its parse
engine, proof runner and skill commands, rather than implement another store.

Files remain the authoring surface. `Rules.save` stores canonical JSON and
its SHA-256 as an immutable draft. Proof pins the body digest and input batch
hash, and says whether the run passed; a failing run stays a draft with its
evidence. Versions feeding MDM need a person's approval, which the agent
records in that person's name with their exact words, the evidence it rests
on and the recording login (rules skill ticket 14): never without a recorded
test run, and for a failing one only with the person's overrule reason.
Status only moves draft → proven → active → retired. One active version per
kind and name is enforced by a partial unique index.

Activation of source mappings and merge policies requires explicit MDM
governance connections and approval. The idempotent MDM handoff commits
first, followed by Rules activation in a separate transaction. Registration
receipts pin dataset readings. A Bookkeeping-only edit does not create a new
MDM mapping. Export retains these receipts along with proof and approval.

`Rules.resolve` exports an active version into content-addressed control
storage during submission. Workers use that frozen export and input manifest,
never YAML or the live Rules database. Retiring a version does not change an
existing run's export. Changing the input reference or operation version
requires a new run. Resume rechecks retained completion evidence; it never
imports a legacy run or invents a missing worklist.

Submission requires a boolean passed proof for the exact Rules digest and a
valid proof batch hash. Mastering operations require exact-digest approval
even under a pipeline document or a target with a different name.

`rules record-proof` records a hashed proof produced by a separate evaluator.
It does **not** perform source parsing tests, named cases, or a Batch Gate.
Claude's planned proof evaluator remains necessary for production approval.
File → DB → file round trips preserve the JSON digest, not comments or YAML
ordering. Approval metadata is not copied into a mutable authoring file.

## Authoring and input manifests

Each existing source has a `bookkeeping` section; graph publication is under
`rules/pipelines/graph-publication/pipeline.yaml`. Targets declare ordered
steps, preceding-step prerequisites, work keys, actual conflicting resource
keys, required checks, lease duration, heartbeat interval and retry policy.
Defaults are 120 seconds, 30 seconds, and five bounded attempts with
exponential backoff capped at five seconds and jitter. Unknown options,
capabilities, missing keys and dependency cycles block execution.

Input worklists belong to the source. They contain identifiers and references,
not business records:

```json
{
  "version": 1,
  "units": [{
    "keys": {"batch_id": "batch-1", "consumer": "mastering/company"},
    "input": {"uri": "s3://bucket/prepared/batch-1.json", "sha256": "<64 lowercase hex characters>"},
    "output": "s3://bucket/control/receipts/batch-1.json",
    "cursor": {"offset": 0}
  }]
}
```

An MDM input artifact contains `{"version":1,"command":{...}}`, an existing
Merge Stage command without `run_id`, preview flags or lease proof. Records
must agree with the source readings frozen in the Rules registration receipt.
A publication input contains `version`, `batch_id`, `consumer`, and an exact
`destination`. Authority is supplied separately by the worker, preserving
the business batch id and request hash on retry.

Version 1 worklists retain their original interpretation and frozen digest:
every configured step gets the listed units. Version 2 declares a separate
bounded worklist for **every** configured step, with independent keys, output
URIs, cursors and counts. A later input may either be an exact URI/hash or
name a unit in one of its declared prerequisites:

```json
{
  "version": 2,
  "steps": {
    "archive": [{
      "keys": {"artifact_id": "batch-1", "destination": "s3://bucket/prepared/batch-1.json"},
      "input": {"uri": "s3://bucket/source/batch-1.json", "sha256": "<64 lowercase hex characters>"},
      "output": "s3://bucket/prepared/batch-1.json",
      "cursor": {"offset": 0}
    }],
    "merge": [{
      "keys": {"batch_id": "batch-1", "consumer": "mastering/company"},
      "input": {"from": {"step": "archive", "key": "batch-1"}},
      "output": "s3://bucket/control/receipts/batch-1.json",
      "cursor": {"offset": 0}
    }]
  }
}
```

This example requires corresponding configured `archive` and `merge` steps;
`merge.requires` must include `archive`. Input selectors use the rendered
work-unit key, not a position or latest-output query. Missing or unknown
steps, absent upstream units, forward references and undeclared dependencies
block submission before a root is created. Empty stages require explicit
`allow_zero_work` even when other stages contain work.

Stage barriers retain their configured order: every prerequisite's unit must
complete before a dependent step can claim work. The stored unit and input
manifest keep the immutable selector. Workers resolve it to the retained
receipt's output URI/hash only after rechecking the prerequisite's evidence,
operation verifier, required checks, and the output bytes. The same checks
follow the complete input chain during resume. Missing or corrupt evidence
blocks execution rather than discovering scope or repeating committed work.
Capabilities still receive an ordinary input reference, so their existing
versions and business idempotency keys are unchanged. Separate publication
intent worklists can follow a merged batch without treating its commit receipt
as a publication command. Final MDM verification checks the MDM worklists
and exact required consumer set.

The `ingest` target accepts a `mdm.ingest` artifact containing `version: 1`,
the same `command` without inline assertions, deferred records or occurrences,
and a `source_input` object with `source_code`, an `artifact` URI/hash,
`publication` (`publication_key`, nonnegative `revision`, optional
`effective_at`) and exact `record_count`. Members must be NDJSON, at most
16 MiB and 1,000 records. The existing adapter creates assertions and retained
deferred evidence from those bytes. It reads the mapping version pinned in
the source Rules registration, never the latest registered mapping. An unseen
Company fixture exercises this entire path without new registry entries or
source callbacks, including a later mapping correction and lost acknowledgement.

MDM steps must lease `mdm:consumer:<command consumer>`; publication steps
must lease `mdm:publication:<consumer>`. Configured batch/consumer keys must
agree with the immutable command. Additional declared resource scopes are
allowed. The guard also covers assessment retention and supersession inside
their own transactions; these occur separately from the master commit.

Lease acquisition sorts resources, rolls back a partially acquired set on
contention, and increments tokens on takeover. Ownership checks use database
time. A destination guard locks its resource rows inside the business
transaction; a deferred check rejects expiry at commit. Bookkeeping completion
has its own deferred authority check. Transactions in different databases
are explicitly separate.

Verified completion and its outbox intent commit together. Delivery uses an
idempotent exact-envelope key in the Change Journal. Lost sink acknowledgements
cause duplicate delivery and reconciliation, never premature completion.
Ordered checkpoints advance only through the contiguous verified prefix.
Completion requires expected-work accounting, configured checks, and all
required journal acknowledgements. Empty work requires explicit configuration
and a verified input manifest.

Owner-only compaction defaults to 30 days. It retains run summaries,
checkpoints, receipt references and lease tokens; pinned or incomplete runs
and pending journal deliveries are retained.

## Local use

Use an isolated PostgreSQL 16 instance. Provisioning creates empty stores and
restricted logins under NOLOGIN owners. It refuses to adopt databases owned by
another workstream. Passwords come from environment variables and are not
printed or committed.

```bash
uv run --extra mdm infra/scripts/provision-clean-bookkeeping.py --rules
```

The script requires `BOOKKEEPING_CLEAN_ADMIN_DATABASE_URL`,
`BOOKKEEPING_CLEAN_RUNTIME_PASSWORD` and, with `--rules`,
`RULES_AGENT_PASSWORD`. Set runtime connection variables to the created
logins. `BOOKKEEPING_MANIFEST_ROOT` names file storage for offline acceptance
or an S3 prefix for AWS.

Existing control databases can be migrated explicitly with
`bookkeeping migrate --runtime-role <role>` and `rules init`, using
`BOOKKEEPING_CLEAN_MIGRATION_DATABASE_URL` and `RULES_MIGRATION_DATABASE_URL`.
Use `bookkeeping init` only to initialize the fresh control schema;
`bookkeeping migrate` refuses a missing schema. `change-journal init` or
`change-journal migrate` and `bookkeeping init-guard` use their separate
migration URLs. They do not populate business or source data. Resource checkpoint and
request authorization migrations retain the five-table control boundary;
see [Change Journal](change-journal.md) for their transaction/recovery contract.

```bash
edgar-warehouse rules save --source gleif --version <new-version> rules/sources/gleif/source.yaml
edgar-warehouse rules record-proof --source gleif --version <new-version> --proof-uri <URI> --proof-sha256 <SHA256>
edgar-warehouse rules pending
# Only on the person's own words, for the version they read.
edgar-warehouse rules approve --source gleif --version <new-version> --evidence <evidence_hash from pending> \
  --by "<name>" --words "<their exact words>"
edgar-warehouse rules activate --source gleif --version <new-version>
edgar-warehouse rules run --source gleif --target mdm --input-manifest <URI> --input-sha256 <SHA256> --limit 100
edgar-warehouse rules run --source gleif --target mdm --resume-run-id <UUID> --limit 100
edgar-warehouse bookkeeping status <UUID>
edgar-warehouse bookkeeping runs --state waiting --limit 100
edgar-warehouse bookkeeping checks <UUID>
edgar-warehouse bookkeeping leases <UUID>
```

Activation of mappings also requires `RULES_MDM_ACTIVATION_DATABASE_URL`.
Fresh source documents declare acquisition authority in Rules and no longer
require a legacy registry connection. The explicit `Rules.activate` Python
legacy registry argument remains for original-stack handoffs. No real rule
versions are approved or activated by this implementation task.

## Verification and remaining acceptance

Mandatory PostgreSQL acceptance has no prerequisite skips:

```bash
uv run --extra mdm --extra s3 pytest tests/integration/test_configured_bookkeeping_postgres.py
```

It runs restricted logins against a disposable `postgres:16-alpine`, testing
independent concurrency, shared-resource contention, renewal/takeover, stale
authority, multiple-resource rollback, ordered checkpoints, commit expiry,
lost acknowledgements, duplicate delivery, journal failure, bad manifests,
processing version drift, zero work, retention, actual Merge Stage commits,
and publication verification failure/recovery. Source files validate against
the same control contract; an unseen source runs without registry edits.

The canonical local PostgreSQL 16 instance was provisioned with empty
`bookkeeping_clean` and `rules` stores, restricted runtime logins, and NOLOGIN
owners. Its control schema has five tables and zero runs; Rules has zero
versions. Acceptance fixtures use separate disposable containers, not these
stores. No AWS state, old Bookkeeping data or active Rules versions were changed.

Verification recorded during implementation:

- Complete configured control acceptance with stage worklists: 42 passed in
  99.96 seconds, no skips. Covers invalid-proof/approval rejection, the operator
  CLI, transformed output chains, different stage counts, lost acknowledgements,
  corrupt prerequisite evidence, and real MDM merge/publication stage order.
- Contract, CLI inventory, Rules files and existing SEC/GLEIF source suites:
  168 passed in 25.23 seconds.
- Existing complete Clean MDM PostgreSQL suite: 56 passed. After adding
  assessment authorization, its eight assessment tests passed again.
- The complete unit/architecture follow-up passed 2,020 tests and 27 subtests
  in 188.28 seconds, with eight existing optional skips. This includes the
  corrected standalone CLI inventory classifications and version 2 contracts.
- Targeted Rules files, CLI inventory and Company/GLEIF source regressions:
  149 passed in 23.79 seconds.
- Wheel build and migration packaging succeeded; `git diff --check` passed.

New submissions print their durable run id on stderr before execution while
leaving result stdout as JSON. `bookkeeping runs` is bounded and also lets an
operator find the root after a lost submission acknowledgement.

Still required before the supplied plan is complete:

1. Convert all existing warehouse orchestration, SEC discovery/parse, silver,
   legacy MDM and Clean MDM RunCoordinator callers. They currently retain
   their old control interfaces. The fresh runner is an additional path, not
   a completed replacement.
2. Reconstruct SEC filing worklists and tracking scope from source-owned
   immutable manifests. Do not relocate source records into the five control
   tables or import old control checkpoints.
3. Bind capture acquisition fences and parse/silver/gold operations to shared
   capability descriptors, preserving current stage order and entry points.
   `artifact.copy` must not be presented as provider API capture or parsing.
   Version 2 now supplies stage-specific worklists and verified-output input
   chains. The business acquisition and transformation capabilities still
   need integration; the transformation used in acceptance is a test fixture.
4. Finish the Rules proof evaluator and runner integration with Claude's
   source engine; qualify SEC and GLEIF end to end, including native source
   continuity, alongside the unseen source and platform jobs.
   MDM dataset registration currently belongs to source documents; platform
   documents declaring their own MDM contracts still need an explicit handoff
   receipt before they can execute mastering.
5. Qualify hosted publication and an isolated full-pipeline build, then
   prepare a reviewed AWS cutover. Retire the old database separately.

No AWS rollout, legacy database reset or retirement is performed here.
