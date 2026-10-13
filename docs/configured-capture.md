# Configured capture, version 1

`provider.capture` is a Python integration through the existing external
worker/verifier protocol. The configured Rust engine checks JSON syntax, the
object root, required members and the empty policy. Bookkeeping enforces frozen
work and leases; Change Journal records authorization and completed evidence.

The offline qualification covers HTTPS JSON objects only, at most 128 MiB and
1–9 requests per second. XML, ZIP, text and `ticker_catalog` completeness are
refused before HTTP. The Company source still selects `artifact.copy` for
capture. Live SEC acquisition, continuation discovery/expansion, producer
manifests and source activation remain Issue 20 L8 work. No fixture constitutes
live source qualification.

## Frozen request

The unit input is an immutable, hash-verified JSON document, at most 1 MiB:

```json
{
  "version": 1,
  "feed": "submissions",
  "url": "https://data.sec.gov/submissions/CIK0000000001.json",
  "scope": {"cik": "0000000001", "file": "CIK0000000001.json"},
  "document": "main",
  "requested_at": "2026-10-12T00:00:00+00:00",
  "requests_per_second": 9
}
```

Optional `previous` is an exact `{uri, sha256}` capture receipt reference.
`document: page` selects approved `page_completeness` and is refused if absent.
The frozen Rules source supplies exact approval/proof, allowed URL prefixes,
scope names, fetch capability and completeness. Unit keys contain the feed and
every scope value. Scope identifies requested work; the completeness contract
does not prove that the provider's returned CIK equals the requested CIK.
Domain identity checks and continuation qualification belong to the subsequent
Company integration.

The profile requires the single provider lease `provider:sec` for all supported
SEC hosts, or `provider:<hostname>` for `http.conditional`. Configure an output
lease as well. Leases remain held through a minimum `1/rate` request period,
including HTTP failures, so separate processes share the rate boundary. Runtime
requires a printable `EDGAR_IDENTITY`; SEC identity must contain an email address.
Redirects and environment HTTP proxies are disabled. Retries belong to control.

For an already approved and submitted run with profile role grants, use the
existing commands, with separate worker and verifier control logins:

```bash
edgar-warehouse workers work provider.capture "$RUN_ID" --limit 1
edgar-warehouse workers verify provider.capture "$RUN_ID" --reports "$REPORTS_URI" --limit 1
```

Set `BOOKKEEPING_CLEAN_DATABASE_URL` to the appropriate login and
`CHANGE_JOURNAL_DATABASE_URL` to the restricted Journal login. These commands
do not author, qualify, approve or activate a Source version.

## Evidence and recovery

Before GET, public renewal validates frozen task binding and live lease
authority; the worker appends and reads back the `acquisition` authorization,
then renews immediately before the request. The outcome uses
`acquisition.outcome`. Both producers retain the logical effect key.

One immutable `<output>.capture.zip` contains two uncompressed entries:
`metadata.json` and `payload`. The payload retains the HTTP entity bytes after
HTTP content decoding, without JSON rewriting. Metadata records request/Rules
references, source/feed/scope, root run/effect, status, validators, byte count,
SHA-256 and UTC capture time. The output JSON receipt references that snapshot
and the acknowledged Journal outcome. File/S3 writes use existing immutable
no-overwrite semantics and readback; output is a file URI offline or S3 in AWS.

A retry with a durable snapshot validates its frozen binding, payload and
acknowledged authorization, then reconciles the outcome and receipt without
GET. Corruption, unreadable storage, Journal outages or orphaned candidates
fail closed. A crash before any complete durable snapshot may repeat the GET;
there is no atomic transaction spanning HTTP, storage and Journal.

A 304 requires a declared predecessor with validators and verified receipt,
Journal authorization/outcome and payload bytes. Its snapshot has no duplicate
body and points directly to the original 200 receipt; chains are flattened.
Current completeness and bounds still apply. The independent verifier reads
the snapshot, reconstructs the receipt, and validates both Journal events before
returning `capture.verified`. Existing readers do not yet consume this receipt
as a Company producer manifest.

Local verification uses offline HTTP only:

```bash
PG16_SERVER=pgserver LC_ALL=C uv run --no-sync pytest \
  tests/unit/test_provider_transport.py \
  tests/engine/test_capture_completeness.py \
  tests/integration/test_configured_capture_postgres.py
```

Install `pgserver` deliberately with `uv pip install pgserver` for the local
PG16 backend; CI uses the required PostgreSQL 16 Docker fixture.
