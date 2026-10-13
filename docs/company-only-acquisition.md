# Local SEC Company route

SEC Company records reach MDM through the source's `mastering` target: one
Bookkeeping run per bundle, every step done by a registered worker and
checked by a separate verifier. Nothing makes a request to SEC here.

1. **Write the input manifest** of a bundle of at most 512 Companies from a
   raw submissions capture (a folder holding `receipts.jsonl` and the
   `bronze/` documents it names):

   ```bash
   uv run --extra mdm --extra s3 edgar-warehouse mdm prepare-clean-company \
     --capture <capture folder> --documents <documents.json> \
     --population <population.json> --name-census <name-census.json> \
     --catalog <ticker catalog receipt key> \
     --capture-run <run id> --catalog-run <run id> --observed-at <instant> \
     --output <bundle folder> --as-of <instant> --revision 0
   ```

   It checks the inputs, binds the approved run IDs and the census digest
   into the contracts and freezes every unit's input; the documents stay in
   the capture, named by their receipts. Its report names the manifest
   (`manifest.uri`, `manifest.sha256`) and the publication.

2. **Run the target** with that manifest:

   ```bash
   uv run --extra mdm --extra s3 edgar-warehouse rules run \
     --source sec.submissions.company --target mastering \
     --input-manifest <URI> --input-sha256 <SHA256>
   ```

   Its steps, in `rules/sources/sec.submissions.company/source.yaml`:
   `main` and `keys` read each document (`census-main.yaml`,
   `census-keys.yaml`, two a unit); `catalog` reads the ticker catalog
   (`catalog.yaml`); `census` reads the Name Frequency file narrowed to the
   bundle's names and CIKs (`census.yaml`, lookup sets derived from the key
   readings); `combine` joins each main unit with the census and the catalog
   (`combine-census-captured.yaml`); `records` prepares the bundle's rows as
   one publication (`mdm.prepare`); `merge` runs it through the Merge Stage
   (`mdm.merge`). The census, combine and records inputs are composed from the
   steps' verified readings. The returned Bookkeeping run ID is the recovery
   handle: `bookkeeping resume <run-id>` for its work and `change-journal
   recover bookkeeping <run-id>` for committed, undelivered Journal intent.

The `mdm` target still merges a manifest prepared elsewhere.

## Configured capture

The registered `provider.capture` worker and independent verifier are qualified
offline for bounded HTTPS JSON objects. Frozen Rules/task authority and an
acknowledged Journal authorization precede each GET. Conditional 304 reuse
verifies prior bytes; recovery after a durable snapshot avoids another GET.
A crash before a complete durable snapshot may repeat the request. See the
[capture contract and commands](configured-capture.md).

## Not here yet

- **Company acquisition integration.** The Company capture target still
  selects `artifact.copy`. The new snapshot/receipt does not replace the
  `receipts.jsonl`/raw-document input above. Producer manifest wiring, exact
  source/Rules qualification and activation remain Issue 20 L8 work; live SEC
  proof needs the operator's permission. Ticker-catalog completeness is outside
  the capture worker's qualified JSON-only scope.
- **Continuation pages.** The raw capture holds main documents and one
  ticker catalog only. Pages named in `filings.files` arrive with capture.

## Local acceptance

`.planning/workstreams/whole-source-census/installed_proof.py` loads an empty
PostgreSQL 16 store only through the installed bundle's workers. Each step is
checked by a verifier in a separate process with its own login. It also kills
a worker mid-run and recovers. On the seven raw-capture bundles it gives
6,414 Companies and 3,052 GLEIF bindings, and a second pass changes nothing.
