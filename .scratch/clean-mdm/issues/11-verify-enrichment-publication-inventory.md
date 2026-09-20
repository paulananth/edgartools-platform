# Verify enrichment publication inventory and continuity before consumption

Type: task
Status: resolved
Owner: Codex
Blocked by: none (10 verified)

## Objective

Satisfy the shared foundation's source-only offline fixture gate before opening
GLEIF Company publication. Reuse immutable acquisition `source_revision` rows;
no new source-publication or root-run table. A source publication is its manifest
plus exactly the declared member revisions under a native publication identity.

## Required work

- Define versioned publication/continuity fields in the approved dataset body.
- Verify the manifest bytes/hash against their immutable revision, and every
  declared member's identity and hashes against immutable acquisition evidence.
  Missing, conflicting, unverified or duplicate member identities fail closed.
- Keep member-file verification distinct from COMPLETE/PARTIAL source coverage;
  a delta can be a complete delivery of a partial source scope.
- Evaluate continuity from the actual source metadata and predecessor proof.
  Prefer a smaller covering delta span when proven; otherwise require a full
  baseline reconciliation for the affected family only.
- Produce a frozen proof for the scoped checkpoint; distinguish consumed bounded
  progress from whole-publication accounting and downstream completion.
- Prove identical source inventories, normalized evidence and hashes from
  reordered/repeated offline delivery with zero Company identities published.
- Preserve original source bytes and ledger history; no physical deletion in
  this implementation slice. Runtime budget/IAM/archive/SLO work remains outside
  the offline acceptance fixture and must pass before hosted activation.

## Inputs

[Pickup reconciliation](../../handover/2026-09-20-codex-company-enrichment-reconciliation.md),
[shared foundation](../../../docs/specs/mdm-enrichment/shared-foundation.md),
[Company source contract](../../gleif-company-augmentation/spec.md), existing
acquisition ledger and the pinned GLEIF research inventory. Synthetic fixture
verification must not be represented as live source qualification or calibrated
matching truth.

## Implementation and verification — 2026-09-20

Implemented the [source-only verifier contract](../../../docs/specs/clean-mdm/source-publications.md)
without new tables, roles or migrations. It verifies exact captured inventories,
raw bytes, interpretation hashes/versions, source coverage and predecessor chains;
recovery proposes the smallest proven delta route or a full reconciliation for
that family. It retains proof metadata without claiming consumption completion.

89 broader regression tests passed, followed by 12 final continuity tests after
adding the completed-native-identity reuse guard; suites overlap by 11 cases.
All passed without skips. [Acceptance evidence](../company-publication-acceptance.json)
pins reports, commands, tested versions and fixture hashes. [Review](../company-publication-review.md).
The real PG16 source-only fixture publishes zero domain records; a separate
rollback/retry test preserves source evidence and atomically retains its proof.

This resolves ticket 11's offline fixture slice, not the entire shared-foundation
release gate. [Ticket 12](12-integrate-native-gleif-company-publications.md) owns
native GLEIF metadata/normalization, verifier integration, authenticated batch
membership and whole-publication accounting. Automatic matching stays disabled.
