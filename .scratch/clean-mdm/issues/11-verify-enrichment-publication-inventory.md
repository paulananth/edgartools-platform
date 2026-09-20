# Verify enrichment publication inventory and continuity before consumption

Type: task
Status: open
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
