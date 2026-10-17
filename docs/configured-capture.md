# Configured capture, version 1

`provider.capture` is a Python integration through the existing external
worker/verifier protocol. The configured Rust engine checks JSON syntax, the
object root (an array root for a POST feed), required members and the empty policy. Bookkeeping enforces frozen
work and leases; Change Journal records authorization and completed evidence.

The offline qualification covers HTTPS JSON objects (and, for a POST feed,
JSON arrays), at most 128 MiB and
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
every scope value. The native completeness contract compiles before HTTP;
unsupported native configuration refuses the request. Scope identifies requested work; the completeness contract
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

Set `BOOKKEEPING_DATABASE_URL` to the appropriate login and
`CHANGE_JOURNAL_DATABASE_URL` to the restricted Journal login. These commands
do not author, qualify, approve or activate a Source version.

## A POST with a key (ticket 92)

A provider whose data is a mapping API (it answers a JSON body of identifiers)
is captured with the fetch capability `https.post`. That one setting means: a
POST of the request's frozen `body` (any JSON value, at most 1 MiB, written in
the request document, so its hash is in the snapshot's `request` reference and
in the Journal evidence), `Content-Type: application/json`, no conditional
headers and no `previous`, and status 200 only. A GET feed's request may not
carry a `body`.

A feed may declare one `secret_header: {name, environment}` (only with
`https.post`): the header's value is read from the named environment variable
for each request and sent only to the provider. It never enters the request,
the snapshot, the receipt, the Journal, a log or an error. A missing or empty
variable stops the capture before the authorization event and before any
request. The operator sets it in their own terminal; it is never typed into a
chat.

A mapping API answers with a JSON array: declare completeness
`format: json_array` with `required: []` (members of an array are not
named); only a POST feed may. A header name the capture sets itself
(`User-Agent`, `Accept`, `Content-Type`, `Content-Length`, `Host`, the
conditional headers) is refused as a secret header. A failed request's error
keeps only its type, so no header rides out in a traceback. A per-job error
inside a 200 answer passes completeness; the reading after capture handles it. Everything else above (approved URL prefix, rate, leases, byte
bound, snapshot, retry without sending again, independent readback) is the
same as for GET.

```json
{"version": 1, "feed": "mapping", "url": "https://provider.example/v3/mapping",
 "scope": {"batch": "0001"}, "document": "main", "requested_at": "2026-10-15T00:00:00+00:00",
 "requests_per_second": 4, "body": [{"idType": "ID_CUSIP", "idValue": "000000000"}]}
```

## Evidence and recovery

Before the request, public renewal validates frozen task binding and live lease
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
fail closed. A crash before any complete durable snapshot may repeat the request (a POST too);
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
