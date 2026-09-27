---
name: bookkeeping
description: Configure, submit, inspect or resume fresh Bookkeeping runs in edgartools-platform. Use for pipeline worklists, leases, checkpoints, completion receipts and journal recovery; source mapping and merge-policy design belong to Rules.
---

# Bookkeeping

Use the shared engine in `edgar_warehouse/bookkeeping/clean/`. It retains
control references and evidence; source records stay in their owning stores.
The protocol and supported boundaries are in
[the specification](../../docs/specs/configured-bookkeeping.md).
Run commands from the repository root with `uv run --extra mdm --extra s3`.
Resolve the skill's physical path for its relative references, and verify the
execution checkout contains the fresh engine; another worktree may be older.

## Establish the task

Determine whether the user wants inspection, recovery, new submission or a
configuration change. Infer source/pipeline, target, environment and bounds
from the request and existing artifacts. Ask only for missing information
that changes the intended work.

Confirm live commands with `edgar-warehouse bookkeeping --help` and
`edgar-warehouse rules run --help` under the `uv run` prefix. Read
`edgar_warehouse/bookkeeping/clean/cli.py` for runtime bindings. Current
operations are `artifact.copy`, `mdm.ingest`, `mdm.merge` and `mdm.publish`.
Artifact copying uses available bytes, not a provider fetch or parser. Export
and graph use offline contract sinks; hosted adapters and full legacy caller
migration remain unfinished. Report unsupported capabilities as gaps rather
than substituting a legacy run.

## Inspect and recover

1. Read bounded `bookkeeping status <run-id> --limit 100` and
   `bookkeeping leases <run-id> --limit 100`. After a lost submission
   acknowledgement, use `bookkeeping runs --limit 100`, optionally with
   `--state`. Match the returned selection before choosing a run.
2. Use `bookkeeping checks <run-id>` for verification. It checks frozen scope
   and may mark a corrupt run blocked. Interpret expected/verified counts,
   failed checks and pending deliveries together; successful status inspection
   is not completion. Read [RECOVERY.md](RECOVERY.md) for incomplete runs.
3. When continuation is authorized, use
   `bookkeeping resume <run-id> --limit 100`. It retains the original manifest,
   processing versions and Rules reading. Keep run and business batch ids;
   skip only units whose retained evidence still verifies.
4. Inspect the result. Completion means `run.state` is `complete`, expected
   work and required checks passed, and pending journal delivery is zero.
   Resume exit code 3 means bounded work remains incomplete; exceptions also
   require inspection. Report remaining work or the concrete blocker.

Supply URLs through the environment without printing credentials.
`BOOKKEEPING_CLEAN_DATABASE_URL` is the fresh runtime connection;
`CHANGE_LEDGER_DATABASE_URL` is needed for continuation/delivery. MDM operations
also need `MDM_DATABASE_URL`. Legacy `BOOKKEEPING_DATABASE_URL` and old run ids
are not fallbacks.

## Submit new work

1. Inspect source-owned artifacts and the active selection with
   `rules status --source <source>` or `--pipeline <pipeline>`. Submission
   also uses `RULES_DATABASE_URL` and `BOOKKEEPING_MANIFEST_ROOT`. Select a
   proven active version with the required approval. Workers consume its
   frozen export, not mutable authoring YAML.
2. Build a bounded source-owned manifest with exact URI/lowercase SHA-256
   references. Use `Artifacts.put`/`put_bytes` for immutable persistence.
   Follow the specification's version 2 example: each configured step has its
   own worklist; predecessor selectors name declared prerequisite step/key
   identities. Preserve stage order and lease actual conflicting resources.
3. Submit through the shared Rules runner, for example:

   ```bash
   uv run --extra mdm --extra s3 edgar-warehouse rules run \
     --source gleif --target ingest \
     --input-manifest "$INPUT_MANIFEST_URI" --input-sha256 "$INPUT_MANIFEST_SHA256" \
     --limit 100
   ```

   Use the requested source or `--pipeline` and supported target. Keep the
   durable run id printed on stderr and inspect the JSON result. A selected
   continuation uses the same selection with `--resume-run-id <run-id>` and
   no replacement input options.
4. Changed inputs, Rules content or processing versions require a new run.
   Existing runs retain their scope. Empty success requires explicit
   configuration and verified manifest evidence.

## Change control configuration

Use `edgar_warehouse.rules.files` to read/write source documents under
`rules/sources/` or platform documents under `rules/pipelines/`. Edit the
intended `bookkeeping` section and preserve source mapping/policy. Consult
`clean/config.py` for exact keys: supported operations, prerequisites, work
keys, conflicting lease scopes and required checks. Source selection uses
configuration, not source-name callbacks.

Save a new Rules version; record only a real evaluator's existing proof with
`rules record-proof`. That command records evidence, not a Batch Gate result
it computed. MDM changes require the person's exact-digest approval under
their own login. Honor an existing approval for that digest; when missing,
explain the Rules governance requirement and await the person's approval.
See the specification for activation and registration. Source documents own
MDM dataset registration; platform-owned MDM contracts still lack handoff
support.

For implementation changes, run the configured contract tests and mandatory
`tests/integration/test_configured_bookkeeping_postgres.py` acceptance on
isolated PostgreSQL 16. Missing prerequisites fail rather than prove success.
Initialization, migration and AWS cutover are separate explicitly scoped
tasks; ordinary recovery neither resets stores nor imports history.

Report selection, commands, verification evidence and concrete remaining gaps.
Record unsupported commands and operational assumptions in the current
workstream's log so later implementation can resolve them.
