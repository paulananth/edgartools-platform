# Research the current-image Apple earnings-8-K content contract

Type: research
Status: resolved
Blocked by: (none)

## Question

Ticket 46 proved that ticket 44's one-byte trailing-newline diagnosis is not
sufficient for the current production image. After a scoped, reversible
one-byte normalization of 45 Apple Item-2.02 primary objects, the current
`bootstrap-batch` image still failed on 18 primary-object immutability checks.
For accession `0000320193-19-000073`, a direct current-gateway comparison
showed 41,169 bytes versus the restored migrated object's 41,278 bytes, with
the first difference at byte 1.

Read-only investigation must establish:

1. Which exact image/dependency/API behavior produces the current attachment
   bytes, and why it differs from the older ticket 44 reproduction.
2. The full byte-diff classification for all 45 affected keys, including
   whether any safe semantic-equivalence rule exists.
3. Whether the right repair preserves migrated bytes and changes attachment
   registration/metadata, pins a compatible fetcher, or needs an explicitly
   governed content migration.
4. A candidate repair's exact failure-closed preconditions and post-repair
   proof before any S3 object is changed again.

Do not mutate AWS, S3 objects, silver, or the immutability guard. Link direct
S3 version, CloudWatch, ECR-image, SEC-source, and code evidence.

## Answer

The safe content contract is **direct byte-preserving SEC HTTP for every
filing document and attachment**. Do not use `Filing.attachments.content` for
earnings or any other immutable bronze artifact. edgartools may still supply
filing/attachment discovery metadata and parsers, but not the persisted
content bytes.

Direct read-only evidence on 2026-07-31 established this for the exact 45
Apple Item-2.02 primary-document keys that failed in
`verify-item202-fix-branchA-1785362507`:

- Current canonical bronze versus
  `sec_client.download_sec_bytes(SEC archival document URL)` matched **45/45**
  byte-for-byte: same length and SHA-256 in three bounded 15-object probes.
- The current deployed task definition is
  `edgartools-prod-medium:96`, immutable image
  `sha256:c48cbddb1bdcdc2b1b3a178fccabf84170ff7130df6b74f48a3e55e74662eca7`
  (`sha-5758680a3c5c`). The lock resolves `edgartools==5.30.0`.
- For representative accession `0000320193-19-000073`, direct SEC HTTP and
  restored bronze are both 41,279 bytes with identical SHA-256; the high-level
  `attachment.content` value is 41,169 bytes and first differs at byte 1.
  This is a transformed representation, not a trailing-newline-only variant.

Therefore the Ticket 46 repair is **not an S3 content migration**. Preserve
the existing migrated bytes. Implement raw document capture so
`write_immutable_bytes` recognizes those bytes as an idempotent reuse, then
registers the missing `sec_raw_object` and `sec_filing_attachment` metadata.
No general normalization equivalence rule, edgartools version pin, or shared
immutability exception is justified.

Graduated implementation: [Implement byte-exact SEC filing artifact
capture](56-implement-byte-exact-sec-filing-artifact-capture.md).
