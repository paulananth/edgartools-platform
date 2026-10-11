# Local SEC Company route

SEC Company records reach MDM in two steps, both through configured workers.
Nothing makes a request to SEC here.

1. **Prepare** a bundle of at most 1,000 Companies from a raw submissions
   capture (a folder holding `receipts.jsonl` and the `bronze/` documents it
   names):

   ```bash
   uv run --extra mdm --extra s3 edgar-warehouse mdm prepare-clean-company \
     --capture <capture folder> --documents <documents.json> \
     --population <population.json> --name-census <name-census.json> \
     --catalog <ticker catalog receipt key> \
     --capture-run <run id> --catalog-run <run id> --observed-at <instant> \
     --output <new bundle folder> --as-of <instant> --revision 0
   ```

   Each main document is read by `rules/sources/sec.submissions.company/census-main.yaml`,
   the Name Census by `census.yaml` and the ticker catalog by `catalog.yaml`.
   Each unit is then combined by `combine-census.yaml`. Every `source.read` and
   `source.combine` unit is run, then verified, and kept in the bundle with
   the bytes it read, so a separate process can check the whole bundle again
   (`verify_company_bundle`). The bundle's `manifest.json` lists the
   records files, cut by the shared batch limits.

2. **Merge** the bundle with the source's `mdm` target: one `mdm.merge` unit
   per manifest, checked by a separate verifier:

   ```bash
   uv run --extra mdm --extra s3 edgar-warehouse rules run \
     --source sec.submissions.company --target mdm \
     --input-manifest <URI> --input-sha256 <SHA256>
   ```

## Not here yet

- **Capture.** `provider.capture`, the worker that fetches from SEC under
  Change Journal authority, is not built (Issue 20 L8). Its live proof needs
  the operator's permission. The capture target returns with it, and so do the
  assertions it must prove again: authorization before the request, a lost
  acknowledgement never refetches, and unchanged links reuse verified bytes.
- **Continuation pages.** The raw capture holds main documents and one
  ticker catalog only. Pages named in `filings.files` arrive with capture.

## Local acceptance

`.planning/workstreams/whole-source-census/installed_proof.py` loads an empty
PostgreSQL 16 store only through the installed bundle's workers. Each step is
checked by a verifier in a separate process with its own login. It also kills
a worker mid-run and recovers. On the seven raw-capture bundles it gives
6,414 Companies and 3,052 GLEIF bindings, and a second pass changes nothing.
