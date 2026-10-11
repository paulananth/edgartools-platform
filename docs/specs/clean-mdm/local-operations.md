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

Owner migration command: `edgar-warehouse mdm migrate
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

After those contracts and a pinned manifest have been registered, mastering
has no `edgar-warehouse` command yet: the `mdm mastering`, `derive-relationships`,
`publish` and `reconcile` commands were deleted (platform validation 2a), and a
Clean MDM run command is an open finding (design review 2026-09-30, finding 3).
Run the Merge Stage as the Proving Run does:
`.scratch/company-mastering/research/27_proving_run.py`.

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

## Count the Name Census

The SEC-to-GLEIF matching rules (ticket 08) bind only a name no other SEC
filer or GLEIF legal entity carries. The census counts that once, over the
whole SEC population (each filer's current and former names) and a full GLEIF
Level 1 Golden Copy (legal and other names, branches excluded). It refuses a
delta. The population file lists the receipt keys of the main submissions
documents counted; each is read from the capture folder (`receipts.jsonl` and
`bronze/`) through `rules/sources/sec.submissions.company/census-raw.yaml` by the
`source.read` worker and its verifier, two documents a unit, and must match its
receipt. The matching cascade is refused while switched on: it has no configured
reading here yet. The Golden Copy arrives as
one verified `source.read` reading of `rules/sources/gleif/census-complete-stream.yaml`
(about an hour for 3.4 million records); the command checks that the reading
projected exactly the names this population holds. It needs local files only:

```bash
edgar-warehouse mdm name-census \
  --capture "$SEC_SUBMISSIONS_CAPTURE" \
  --population "$SEC_POPULATION_JSON" \
  --gleif-reading "$GLEIF_CENSUS_READING_JSON" \
  --gleif-reading-sha256 "$GLEIF_CENSUS_READING_SHA256" \
  --gleif-metadata "$GLEIF_LEVEL1_METADATA_JSON" \
  --output "$NAME_CENSUS_JSON"
```

The metadata file holds the archive's verified publication metadata
(`format`, `cdf_version`, `content_date`, `file_content`, `record_count`); its
record count must equal the reading's. Rebuild the census for each full Golden
Copy: a census counted before a new GLEIF entity took a name cannot see it.

## Prepare a native Company sample

This command needs local files and no database credentials:

```bash
edgar-warehouse mdm prepare-clean-company \
  --capture "$SEC_SUBMISSIONS_CAPTURE" \
  --documents "$BUNDLE_DOCUMENTS_JSON" \
  --population "$SEC_POPULATION_JSON" \
  --catalog warehouse/bronze/reference/sec/company_tickers_exchange/2026/09/02/company_tickers_exchange.json \
  --capture-run "$CAPTURE_RUN_ID" --catalog-run "$CATALOG_RUN_ID" \
  --observed-at 2026-09-30T02:20:28+00:00 \
  --name-census "$NAME_CENSUS_JSON" \
  --output "$CLEAN_MDM_INPUT_DIRECTORY" \
  --as-of 2026-09-19T00:00:00Z --revision 0
```

It reads the raw capture: each main submissions document named in
`--documents` (at most 1,000 receipt keys, all in the population the Name
Census counted), by its receipt in `receipts.jsonl`, and SEC's exchange
ticker catalog (`--catalog`, a receipt key). The configured workers read each
document in units of one or two (`census-main.yaml`), read the census once
narrowed to the bundle's name keys (`census.yaml`, bound to the census's
digest), read the catalog once (`catalog.yaml`), and combine them per Company
(`combine-census.yaml`): forms from the document's recent filings, tickers
from the catalog in rank order, the business address and the census entry.
Every worker is executed and verified, and its inputs and outputs are kept
under `workers/`. The capture and catalog run IDs and the observation time
are the caller's facts, bound into every row. Each record names its bronze
document (`_origin.bronze`: key, receipt sha256). The bundle's publication
key names the capture run, the documents' digest, the catalog run and
receipt, and the census digest; a different catalog or census is a different
publication. An existing different bundle is rejected; identical preparation
is idempotent.
The explicit revision is source-publication order, not ingestion order. Only
SEC `operating` filers and qualifying `other` filers can become Companies;
nullable text fields are supported.
Malformed/unsupported rows are retained with blocking reviews during ingestion.
No deferred-resolution capability exists yet. Source record counts include
duplicate occurrences; identical assertions have one business effect.

The preparation does not activate source coverage or allocate identities.
Unknown effective time remains unknown; a sample never retires absent records.

### Name each record's bronze object

The latest-only Stage keeps, for each source record, the bronze object its
winning source extract came from (ticket 10). Preparation reads each document
by its receipt in the capture's `receipts.jsonl`, so every Company record
carries `_origin.bronze` (object key, sha256, locator `$`: the whole
document), and its `raw_object_id` is that sha256. The record itself is
unchanged. A GLEIF record's bronze object comes from its verified native
publication.
Apply owner migrations and approved registry/dataset/policy registration before
using its manifest with the normal bounded Clean MDM commands.
