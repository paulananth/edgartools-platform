# Integrate native GLEIF publications and Company consumption accounting

Type: task
Status: in progress
Owner: Codex — codex/company-native-gleif
Blocked by: none (11 offline verification passed)

## Objective

Connect approved native GLEIF evidence to the source verifier and bounded Company
consumer before enabling SEC + GLEIF mastering. Ticket 11's synthetic source-only
fixture is a foundation check, not a native loader or calibrated matching rule.

## Required work

- Pin approved source artifacts or acquisition publication IDs. Preserve source
  metadata, original bytes, schema and parser versions. Do not silently select the
  three-Company pilot or use the research seed links as independent match truth.
- Map native release ordering and predecessor metadata to a versioned publication
  contract; fail unsupported metadata. Verify L1 + RR + REPEX as Golden Copy;
  OpenCorporates remains an independent corroboration publication.
- Qualify native JSON ZIP (the restored research format) and XML ZIP size and
  streaming limits, canonical/domain hashes,
  source kinds, lifecycle corrections, parent/exception interpretation and exact
  normalized/deferred record accounting. Keep unsupported domains as evidence.
- Wire source verification before Merge Stage and authenticate bounded input
  membership. Freeze the selected recovery plan in existing run inputs; establish
  fully consumed publication predecessors from exact accounting, never partial
  checkpoint positions. Resume without missing or duplicate work.
- Demonstrate SEC + GLEIF Company assertions and governed field provenance through
  the shared transaction boundary, preserving source delivery, whole-publication
  consumption and downstream completion as distinct gates.
- Use the shared rules-as-data design for classification, binding and field
  selection. Company Q14 allows identifier-only binding through a verified
  Identifier Contract; fuzzy binding and consolidation retain their separate
  statistical gates. Do not activate rules before their predicates and evidence
  paths are implemented and tested. Company remains the priority over other entities.

## 2026-09-20 prerequisite checkpoint

Rebased the four Company foundation commits onto `origin/main` `dfe5eefe`,
including Claude's Mastering Policy Language proposal. The existing foundation
passed 90 focused tests with real PostgreSQL 16 and no skips.

Restored all three September 11 archives outside git and verified hashes, sizes
and ZIP CRCs. Full-source extraction reproduces all three retained extracts
byte-for-byte; cohort, finalization and attribute analysis reproduce too.
This is historical research verification, not a calibrated rule or rebuild
approval. Native integration and full-publication consumption remain unfinished.

See [reconciliation and continuation requirements](../../handover/2026-09-20-codex-policy-language-reconciliation.md)
and [machine-readable evidence](../research-reverification-20260920.json).

## Inputs

[Publication verifier contract](../../../docs/specs/clean-mdm/source-publications.md),
[Company policy](../../../docs/specs/clean-mdm/company-policy.md),
[Company completion gate](../../../docs/specs/clean-mdm/company-completion.md),
[Claude pickup reconciliation](../../handover/2026-09-20-codex-company-enrichment-reconciliation.md).
