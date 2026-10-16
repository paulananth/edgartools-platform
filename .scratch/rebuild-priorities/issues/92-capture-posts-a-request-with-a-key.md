# The configured capture posts a request with a key

Priority: 92, tier 2. Map: [Rebuild priorities](../map.md).

Type: task (engine). Status: done (2026-10-16 08:21 ET): #994 merged. Unblocks: 80 (Onboard OpenFIGI with the skills).

## Why

Operator, 2026-10-15: "Maybe we onboard fIGI first", then "Both, in parallel" (the N-PORT Security test run now; ticket 80's capture set up beside it).

The configured capture (`edgar_warehouse/workers/provider_capture.py` over `provider_transport.py`) makes one bounded, authorized **GET**: an approved URL prefix, a User-Agent, a shared provider lease, the rate held through the request, one immutable snapshot, an independent readback. OpenFIGI publishes no bulk file. Its mapping is `POST /v3/mapping` with a JSON array of up to 100 identifiers and a free key in the `X-OPENFIGI-APIKEY` header (ticket 80, "What the source is"). The capture cannot send either today.

## What changes

- A capture request may declare `method: POST` with a body. The body is frozen with the request, so the snapshot names exactly what was asked, and a retry reuses the snapshot without sending again.
- An approved capture configuration may name **one secret header**, taken from an environment variable the configuration names (`OPENFIGI_API_KEY`). It is never written into the request, the snapshot, a receipt, a log or an error. A missing variable stops the capture before any request. The operator sets the key in their own terminal.
- The approved URL prefix, the rate (OpenFIGI's 25 requests every 6 seconds with a key is about 4.17 a second: declare `requests_per_second: 4`), the lease, the byte bound and the readback stay as they are.
- Nothing else about GET captures changes.

## Checklist

- [x] The operator's word to code it: "Code 92 and test (Recommended)" (2026-10-15, answering "Do I have your word to code ticket 92 ... and then to run a first small test capture"); approved URL from the operator: `https://api.openfigi.com/v3` ("Use this url"); the documentation page shows the Apache 2.0 licence
- [x] GoF consult before code: the fetch capability (`https.post`) is the one setting, not a second `request.method`; POST as keyword arguments of `fetch` so the GET safety code is not copied (2026-10-15 12:16 ET)
- [x] POST with a frozen body; one secret header from a named environment variable, never stored; completeness `json_array` (2026-10-15 12:33 ET)
- [x] Tests offline only (httpx MockTransport, no provider request): body sent and frozen, a retry reuses the snapshot, the key header sent and found in no written byte, a missing key refused before any request, a POST without body, a GET with a body and an object answer refused; GET captures unchanged. 60 unit and 41 integration (disposable PostgreSQL 16) tests pass (2026-10-15 12:33 ET)
- [x] `docs/configured-capture.md`, "A POST with a key" (the capture's own page; READING.md has no capture section) (2026-10-15 12:41 ET)
- [x] Three-axis review (Standards, Spec, GoF). Fixed: the key's header may not be one the capture sets itself (`User-Agent`, `Content-Type` and the rest); an array answer is for a POST feed only; a failed request's error keeps only its type, so the key never rides out in a traceback; the key read and the request's method, body and headers in one function (`_sending`); a test finds the key in no written file and no Journal or control row; stale "GET" wording; the rate set at 4 a second (25 every 6 s is 4.17). 69 unit and 42 integration tests pass (2026-10-15 12:41 ET)
- [x] One small real request to OpenFIGI (operator: "Code 92 and test", then "Reuse the OPENFIGI_API_KEY": the key kept in a private file outside the repository, mode 600, loaded only for the command): one POST of 100 N-PORT CUSIPs through `provider_transport.fetch`, status 200, a JSON array of 100 answers, receipt (sha256, bytes) beside it on this machine; findings on ticket 80 (2026-10-15 13:02 ET)
- [x] PR, CI green, merge on the operator's word: #994 merged 2026-10-15 13:11 ET
- [x] Learning → skill: `docs/configured-capture.md` (how a POST feed with a key is declared and kept safe); the data-onboarding skill's capture rows belong to Bookkeeping, unchanged (2026-10-15 12:41 ET)
