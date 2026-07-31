# Implement byte-exact SEC filing artifact capture

Type: task
Status: claimed
Blocked by: 55

## Question

How must filing-document and attachment capture use the repository-owned,
byte-preserving SEC HTTP client so immutable bronze always represents the SEC
archival document, while retaining edgartools only for filing discovery
metadata and parsers?

## Required work

- Keep edgartools filing/attachment discovery metadata, but never persist
  `attachment.content` bytes for a filing artifact.
- Fetch each selected attachment's canonical SEC archival URL through the
  repository-owned raw SEC client; do not route this content path through
  edgartools HTTP or high-level content accessors.
- Preserve cache/silver-once skips, URL allowlisting, bounded retries,
  observability, attachment discovery (including multi-attachment forms), and
  exact per-artifact network metrics.
- Replace Ticket 06's edgartools-only architecture guard with one that permits
  this narrow content gateway and prohibits transformed content persistence or
  a second ungoverned SEC client.
- Keep `write_immutable_bytes` byte-exact and fail-closed. Existing bronze that
  equals the direct SEC response must be reused without a new S3 version, then
  registered in `sec_raw_object` and `sec_filing_attachment`.
- Add unit and architecture coverage for raw-byte persistence, a transformed
  edgartools-content adversary, multi-attachment discovery, exact-content
  reuse, and non-identical conflict failure.
- After a deployed immutable image passes focused tests, run the bounded Apple
  artifact-registration and per-filing verification required by Ticket 46.

## Done when

The repository proves that every persisted filing artifact is the exact direct
SEC response, historical byte-exact bronze is reused rather than rewritten,
and the Apple F5 pilot reaches `sec_earnings_release` without relaxing the
immutable-object guard.
