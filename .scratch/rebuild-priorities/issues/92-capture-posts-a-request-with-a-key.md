# The configured capture posts a request with a key

Priority: 92, tier 2. Map: [Rebuild priorities](../map.md).

Type: task (engine). Status: in progress (branch `claude/openfigi-capture`). Unblocks: 80 (Onboard OpenFIGI with the skills).

## Why

Operator, 2026-10-15: "Maybe we onboard fIGI first", then "Both, in parallel" (the N-PORT Security test run now; ticket 80's capture set up beside it).

The configured capture (`edgar_warehouse/workers/provider_capture.py` over `provider_transport.py`) makes one bounded, authorized **GET**: an approved URL prefix, a User-Agent, a shared provider lease, the rate held through the request, one immutable snapshot, an independent readback. OpenFIGI publishes no bulk file. Its mapping is `POST /v3/mapping` with a JSON array of up to 100 identifiers and a free key in the `X-OPENFIGI-APIKEY` header (ticket 80, "What the source is"). The capture cannot send either today.

## What changes

- A capture request may declare `method: POST` with a body. The body is frozen with the request, so the snapshot names exactly what was asked, and a retry reuses the snapshot without sending again.
- An approved capture configuration may name **one secret header**, taken from an environment variable the configuration names (`OPENFIGI_API_KEY`). It is never written into the request, the snapshot, a receipt, a log or an error. A missing variable stops the capture before any request. The operator sets the key in their own terminal.
- The approved URL prefix, the rate (OpenFIGI's 25 requests every 6 seconds with a key fits the 1-9 a second bound), the lease, the byte bound and the readback stay as they are.
- Nothing else about GET captures changes.

## Checklist

- [x] The operator's word to code it: "Code 92 and test (Recommended)" (2026-10-15, answering "Do I have your word to code ticket 92 ... and then to run a first small test capture"); approved URL from the operator: `https://api.openfigi.com/v3` ("Use this url"); the documentation page shows the Apache 2.0 licence
- [x] GoF consult before code: the fetch capability (`https.post`) is the one setting, not a second `request.method`; POST as keyword arguments of `fetch` so the GET safety code is not copied (2026-10-15 12:16 ET)
- [x] POST with a frozen body; one secret header from a named environment variable, never stored; completeness `json_array` (2026-10-15 12:33 ET)
- [x] Tests offline only (httpx MockTransport, no provider request): body sent and frozen, a retry reuses the snapshot, the key header sent and found in no written byte, a missing key refused before any request, a POST without body, a GET with a body and an object answer refused; GET captures unchanged. 60 unit and 41 integration (disposable PostgreSQL 16) tests pass (2026-10-15 12:33 ET)
- [ ] READING.md or the data-platform skill's capture section; three-axis review; PR, CI green, merge on the operator's word
- [ ] Learning → skill
