# Local operation and reversal procedure

Status: implemented local commands, bounded Company preparation and opt-in
read API. Other native adapters, hosted materialization and production
qualification are pending. See [state of the build](state-of-build.md).

## Acceptance runner

Use Colima/Docker with `postgres:16-alpine` available. The runner creates unique
disposable containers and databases; it fails rather than skips missing
prerequisites. The API checks need the existing `mdm` extra as well as
`mdm-runtime`:

```bash
uv run --frozen --extra s3 --extra mdm-runtime --extra mdm pytest \
  tests/integration/test_clean_mdm_postgres.py \
  tests/mdm/test_api.py \
  tests/mdm/test_publication_drain_cli.py \
  tests/mdm/test_graph_publication_queue.py -q --tb=short
```

These tests require no Snowflake credentials or network source access. The
synthetic fixture manifest under `tests/fixtures/clean_mdm/v1` is acceptance
data, not an approved production source manifest or matching calibration set.

## Database and command boundaries

`MDM_DATABASE_URL` contains the master projection, immutable evidence, decisions,
attempt events and publication outbox. `CHANGE_LEDGER_DATABASE_URL` contains the
acquisition history and immutable MDM event mirror. `BOOKKEEPING_DATABASE_URL`
contains the existing root `pipeline_run`. One UUID identifies the root across
all three. No transaction is claimed across databases.

Owner migration command: `edgar-warehouse mdm migrate --model clean
--application-role application`. Migrations 023 and 025–030 are checksummed.
Migration 027 adds immutable deferred evidence. Migration 028 adds
[candidate assessments](candidate-assessments.md), durable-before-application
coverage and a rollback-only preview capability. Older commit capabilities
remain inaccessible to the runtime role. Migration 029 adds independently
fenced [family checkpoints](family-checkpoints.md) and preserves old unscoped
commands.
Migration 030 enforces Dataset Contract dispositions for retained evidence;
undeclared reasons remain blocking. See [native GLEIF operation](native-gleif.md)
for authenticated ranges, source consumption and its production throughput limit.
Mirror installation uses `clean.publication.migrate_mirror` with migration 024
and a separate owner connection. Runtime commands select
`MDM_APPLICATION_ROLE` (default `application`) and cannot write the tables
directly. Dataset registration and policy registration use owner-only functions
in `clean.store`; dataset contracts must attest an active, approved acquisition
registry version. Do not manufacture activation authority to make a run pass.

After those contracts and a pinned manifest have been registered:

```bash
edgar-warehouse mdm mastering --model clean --manifest "$CLEAN_MDM_MANIFEST" \
  --run-id "$CLEAN_MDM_RUN_ID" --limit 100
edgar-warehouse mdm derive-relationships --model clean --manifest "$CLEAN_MDM_MANIFEST" \
  --run-id "$CLEAN_MDM_RUN_ID" --limit 100
edgar-warehouse mdm publish --model clean --consumer journal --run-id "$CLEAN_MDM_RUN_ID" --limit 100
edgar-warehouse mdm publish --model clean --consumer export --run-id "$CLEAN_MDM_RUN_ID" \
  --contract-output "$CLEAN_MDM_CONTRACT_OUTPUT" --limit 100
edgar-warehouse mdm publish --model clean --consumer graph --run-id "$CLEAN_MDM_RUN_ID" \
  --contract-output "$CLEAN_MDM_CONTRACT_OUTPUT" --limit 100
edgar-warehouse mdm reconcile --model clean --run-id "$CLEAN_MDM_RUN_ID"
```

Repeat bounded stages until their frozen batches are observed. Manifest order
is authoritative; a later stage cannot pass missing preceding batches. An
atomic batch larger than `--limit` produces an actionable error instead of
silently making no progress. Previously observed batches do not consume the
limit. Source members are hash-verified and parsed from the same bounded bytes.

Export and graph commands above verify immutable **local contract artifacts**.
They are not hosted consumers. Publication drains the consumer queue in global
generation order, including older runs. A stage exit code of zero means that
invocation succeeded; only `reconcile` returning zero with
`end_to_end_complete=true` proves completion of the frozen local contract.
Incomplete reconciliation/status exits with code 2. Review resolution in a
later batch must itself finish publication before it can clear the root run.

## Investigate and reverse a merge

1. Read the retained merge decision, its original evidence, later corrections
   and dependent merge decisions. Use generation-pinned reads to compare the
   accepted identities before and after consolidation.
2. Prepare a new stewardship manifest with a `reverse` decision referencing
   the original decision ID, named actor, reason and effective timestamp.
   Dependent merges must be re-adjudicated; the operation rejects an unresolved
   dependency. Reuse the new reversal root UUID across its subsequent stages.
3. Run `mdm apply-decisions --manifest "$CLEAN_MDM_REVERSAL_MANIFEST"
   --run-id "$CLEAN_MDM_REVERSAL_RUN_ID" --limit 100 --dry-run`.
   Preview executes the same merge and SQL validation and rolls back every
   effect. It returns the next atomic batch's proposed identities, fields,
   aliases, relationships and review dispositions without registering a new
   Bookkeeping root or publication intent. Inspect retained earlier generations
   for the corresponding before-state.
4. Apply the reviewed manifest without `--dry-run`. Checkpoints and dependencies
   are checked again; a preview does not reserve state or authorize a changed
   manifest. The reverse decision restores partitions from retained evidence,
   preserves later valid corrections and establishes a Match Exclusion.
5. Drain all required consumers and reconcile the reversal root. Investigate
   ambiguous facts through their review evidence; an unresolved required review
   blocks completion. Revoking a reversal's exclusion does not silently reinstate
   the original merge.

Components exceeding 10,000 retained closure records are rejected without any
business effects. Staged large-component reversal remains unimplemented and is
a release limitation; an operator must not split a dependent reversal into
independently visible partial commits.

## Version-2 read API

Set `MDM_ENABLE_V2_API=1` only in the intended local/rehearsal API process.
Existing `X-API-Key` authentication applies. Version 1 continues using retained
legacy contracts; no compatibility crosswalk or consumer cutover is implied.

- `GET /api/v2/mdm/entities/{uuid}?generation=N` returns requested/canonical IDs,
  identity kind, profiles, field and role-field provenance, the content hash,
  and projection generation/as-of/policy/origin run.
- `GET /api/v2/mdm/objects/{entity|relationship|review}?limit=100` starts a
  bounded snapshot page. Keep its `generation` and pass `next_after` as `after`
  for subsequent pages. Retired relationships and closed reviews are explicit
  markers, so consumers can remove obsolete objects.

Snapshot generation and each object's projection as-of are distinct: an object
may have been last projected before the selected global generation. Future or
missing generations return 404. An unconfigured v2 API has no v2 routes.

## Prepare a native Company sample

This command needs local files and no database credentials:

```bash
edgar-warehouse mdm prepare-clean-company \
  --landing-root "$COMPANY_LANDING_ROOT" \
  --landing-manifest "$COMPANY_LANDING_MANIFEST" \
  --output "$CLEAN_MDM_INPUT_DIRECTORY" \
  --as-of 2026-09-19T00:00:00Z --revision 0 --limit 3
```

It copies and hashes the original Company Parquet and landing manifest, emits
bounded JSONL, and writes reviewable dataset/policy/manifest/inventory files.
An existing different bundle is rejected; identical preparation is idempotent.
The explicit revision is source-publication order, not ingestion order. Only
`operating` companies and nullable text fields are currently supported.
Malformed/unsupported rows are retained with blocking reviews during ingestion.
No deferred-resolution capability exists yet. Source record counts include
duplicate occurrences; identical assertions have one business effect.

The preparation does not activate source coverage or allocate identities.
Unknown effective time remains unknown; a sample never retires absent records.
Apply owner migrations and approved registry/dataset/policy registration before
using its manifest with the normal bounded Clean MDM commands.
