# Capture integration contract

Keep the existing function/worker seams (GoF review of sec_client and worker
history); no new provider hierarchy or Bookkeeping callback registry.

Version 1 is bounded HTTPS JSON-object acquisition (including configured SEC
main/page objects), <=128 MiB, <=9 requests/second. Other completeness formats,
including ticker_catalog, are explicitly unsupported in this slice.
The approved Source Rules envelope supplies URL prefixes, scope names and
completeness; a frozen unit supplies feed, exact URL/scope, main/page selection,
requested_at, rate and an optional prior capture receipt. Every field is checked
before HTTP. Root input/rules binding is checked by the existing public renewal
protocol, strengthened generically to compare the frozen task first. Workers
receive no controller object/engine. The provider-wide lease is mandatory and
held through a minimum request period, including failures, across processes.

Before GET: renew and validate task, append/read back acknowledged authorization
intent, then renew again immediately before the socket request. Source authorizes
SEC hosts via sec.conditional; redirects, proxy-environment substitution and
unsupported formats/bounds fail closed. There is no transport retry loop.

One immutable ZIP_STORED snapshot carries metadata and original payload bytes.
It is written atomically with existing Artifacts file/S3 no-overwrite semantics;
its response metadata and body are never persisted separately or overwritten.
The snapshot is evidence, not mutable control state. A deterministic output
receipt references it; a durable snapshot discovered on retry is independently
validated and reconciled to the Journal/receipt without another GET. A crash
before any complete snapshot remains an uncompleted GET and may retry. No
exactly-once claim is made for an unrecorded network exchange.

304 snapshots carry no duplicate body: they name an authenticated prior capture
receipt, bound to the same source/feed/URL/scope, and reuse its verified payload.
Prior snapshots must be direct 200 captures: reusing a chain is flattened to that
original receipt. Responses are checked by configured Rust JSON assertions;
metadata/receipt framing, SHA checks and HTTP orchestration remain Python.
Verifier reconstructs the receipt, raw payload/hash, configuration and durable
Journal acknowledgement independently, and reports capture.verified only.

Initial release is a registered, independently qualified profile. Existing
Company capture configuration is not silently switched from artifact.copy, and
there is no Source activation or SEC request. Wiring producer manifests,
continuation expansion, public provider qualification and exact Rules switch-on
remain the authorized next integration step of Issue 20 L8. Source versions with
unsupported formats are rejected before any request.
