# Configured 13F source extract worker

The `source.read` worker runs captured 13F information tables through the Rust
engine's Python facade. Field paths, missing tokens, root checking and parser
limits are declared in `crates/source-contract/contracts/thirteenf/contract.yaml`.
The platform wheel includes that same file as
`edgar_warehouse/config/source_contracts/thirteenf.yaml`.

The contract declares two threads and at most two artifacts per task, with
32 MiB and 100,000 rows per artifact. Capture and downstream persistence remain
separate work. The worker writes configured tables and deferred records as
immutable JSON; this change does not activate a feed, master securities or
publish holdings to a database.

## Frozen inputs

Each work unit's input is a content-addressed JSON manifest:

```json
{
  "version": 1,
  "contract": {"uri": "s3://YOUR-BUCKET/contracts/13f.yaml", "sha256": "ACTUAL_SHA256"},
  "artifacts": [
    {"uri": "s3://YOUR-BUCKET/bronze/filing.xml", "sha256": "ACTUAL_SHA256"}
  ]
}
```

Copy the contract to an immutable object and pin its actual byte digest. Pin
each captured XML object's actual digest. List one or two artifacts per manifest;
no discovery occurs during work or resume. The outer Bookkeeping input manifest
uses ordinary version-1 units (`keys`, `input`, `output`, `cursor`), with a unique
`batch_id` key and immutable output URI per batch. Its `input` reference points
at the manifest above. The output includes the pinned contract, every input
reference, full tables and deferred records. Missing or altered inputs fail;
malformed XML outside the root fails. A conflicting existing output fails.

## Rules and worker commands

Install the platform with its `engine` extra, or use the existing dependency
images, which include a prebuilt engine wheel. Save, prove and approve the
`rules/pipelines/sec-13f-reading/pipeline.yaml` version through the normal Rules
lifecycle before submission. Neither this document nor installing the worker
approves or activates a Rules version.

Grant the `source.read` profile to the worker and verifier identities using the
existing Bookkeeping profile-grant command. Keep their logins separate, and use
AWS S3 output/report roots for AWS runs. Submit a frozen worklist:

```bash
uv run --extra engine edgar-warehouse rules run --pipeline sec-13f-reading --target read \
  --input-manifest s3://YOUR-BUCKET/manifests/WORKLIST.json --input-sha256 ACTUAL_SHA256
uv run --extra engine python -m edgar_warehouse.workers work source.read RUN_ID --limit 1
# Set BOOKKEEPING_CLEAN_DATABASE_URL to the verifier's separate login.
uv run --extra engine python -m edgar_warehouse.workers verify source.read RUN_ID \
  --reports s3://YOUR-BUCKET/verification-reports/ --limit 1
uv run --extra engine edgar-warehouse bookkeeping finalize RUN_ID
```

The worker renews its lease while parsing. A successful write is only a
candidate; verification recomputes the configured source extract and compares the
complete destination bytes. Bookkeeping independently checks the input hash,
output receipt, lease and report bindings before admitting completion.
The runtime digest includes the worker, protocol client, Rules loader, facade,
value registry and loaded native binary. The YAML itself is pinned in the input.

For qualification only, `file://` references use the same immutable artifact
adapter offline. The actual PostgreSQL 16 test exercises submission, work,
separate verification and finalization; no prerequisite is skipped.

## Performance evidence

The [100-filing rerun](research/rust-13f-yaml-rerun-2026-10-02.md) verified all
331,039 output rows against the previous hashes. The updated callback-free
Rust/Python facade had a 14.02-second two-worker median. The host was busy, so
these parser measurements do not establish production pipeline speed or a
native Rust advantage. This worker also reads/writes and verifies durable output;
that work was outside the timing boundary.

The final release worker was also [qualified through execute and verify](../.planning/workstreams/13f-configured-worker/corpus-qualification.json) on all 100 filings: 331,039 rows, identical prior hashes, in 70.2 seconds. That duration includes immutable writes and a second parse for verification and is not comparable to the parser-only timing table.
