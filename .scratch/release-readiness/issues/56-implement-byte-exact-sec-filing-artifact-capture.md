# Implement byte-exact SEC filing artifact capture

Type: task
Status: resolved
Blocked by: none

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

## Progress (2026-08-01)

Implementation landed in `5ca30418422c629be68a3d68c7f6a7eadd10d9c7`
(`fix(bronze): capture filing artifacts as raw SEC bytes`):

- edgartools supplies only filing and attachment discovery metadata.
- `filing_content_gateway.download_filing_content_bytes` is the one narrow
  raw-SEC adapter used for persisted document bytes.
- The artifact path preserves cache/silver skip behavior, URL-based
  attachment discovery, immutable exact-content reuse, fail-closed content
  conflicts, and per-document network events/metrics.
- Architecture checks prohibit direct raw-client use outside the adapter and
  prohibit transformed `attachment.content` persistence.

Focused verification passed on 2026-08-01: 51 tests across filing gateway,
edgartools gateway, loader idempotency, and architecture boundaries; Ruff
also passed for the touched implementation and test files.

The production deployment and bounded Apple validation are recorded below.
The immutable-object guard remains fail-closed.

## Resolution (2026-08-01 — operator accepted implementation scope)

The immutable warehouse image
`sha256:344912ff48228e7915d850c8180b56083852b8dcb86075d8680fe8dbfaa0bf2c`
was deployed as `edgartools-prod-medium:103`. Two bounded Apple tasks then
completed successfully: artifact registration
`apple-byte-exact-artifacts-20260801T1101Z` and per-filing
`apple-byte-exact-per-filing-20260801T1125Z`.

The published silver artifact proves that all 45 Apple Item-2.02 accessions
have both a `sec_raw_object` and primary `sec_filing_attachment` row. A direct
SEC-versus-bronze read of `0000320193-19-000073` was byte-exact: both were
41,279 bytes with SHA-256
`5abdda123104e41b3cebf04602df6cfd93973c02515f56ad4f247c29f3383ae2`.
The new registration task was an idempotent skip (164 silver skips, zero
network fetches), preserving immutable existing bronze as intended.

The separate per-filing task exited 0 after parsing 75 of 118 filings, but
reported `rows_earnings_release: 0`. That is an outstanding F5 parser/output
problem under Ticket 42/Ticket 46; it does not invalidate the raw-byte capture
or immutable-registration implementation. Ticket 56 is resolved as the
implemented and production-validated byte-exact capture boundary.
