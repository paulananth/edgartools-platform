# MDM Enrichment Shared Foundation

Label: `wayfinder:map`

## Destination

A decision-complete specification input for `docs/specs/mdm-enrichment/shared-foundation.md`
(workstream 00 of the [MDM Enrichment Program](../mdm-enrichment-program/map.md)):
one AWS source-evidence path supporting every enrichment source and consumer
— temporary Bronze staging, a low-cost immutable Source Artifact Archive,
source/run identity, independent checkpoints, temporal versions, review
states, replay, observability, security, and retention hooks. Planning only:
the spec itself, and any implementation, stay blocked until this map's
decisions are locked and (per the existing GoF review) an offline fixture
proves inventories, state transitions, and evidence hashes reproduce
identically without publishing a domain record.

This map exists because [GLEIF MDM enrichment evidence](../gleif-company-augmentation/map.md)'s
[ticket 17](../gleif-company-augmentation/issues/17-write-and-verify-gleif-mdm-spec.md)
(the Company/GLEIF consumer spec) is blocked on this foundation spec, which
had never itself been through a decision process.

## Notes

- Parent program: [MDM Enrichment Program](../mdm-enrichment-program/map.md).
  Stewardship of that program (and its children) was taken over from Codex in
  a prior session (commit `f3fe8beb`) — this map continues that stewardship,
  not a fresh takeover.
- **Primary input, already done**: Codex's own
  [GoF design review](../../docs/design-reports/mdm-enrichment-shared-foundation-gof-review-2026-09-13.md)
  (13 September 2026) already surveyed this exact frontier — verdict
  "proceed to the shared-foundation specification, but do not open
  implementation work yet," Strategy pattern recommended at the
  source-publication seam, and a named list of 7 open specification
  decisions (its Appendix C) plus a 5-item minimum schema boundary (its
  finding 4). This map's tickets are those 7 items, not a re-derivation from
  scratch — the review's own recommendations are cited as the default answer
  wherever it gave one.
- Checked live, this session: **no `spec.md` exists anywhere** —
  `origin/main`, `origin/codex/clean-mdm`, and `origin/codex/clean-mdm-integration`
  all lack `docs/specs/mdm-enrichment/shared-foundation.md` and
  `.scratch/gleif-company-augmentation/spec.md`. Nothing to reverify; this is
  fresh decision work.
- **Locked, 2026-09-19 (operator directive)**: legacy MDM will be
  decommissioned. **Do not build anything against legacy MDM.** Clean MDM's
  `mdm_v2` schema (`.scratch/clean-mdm/`, Codex/Grok-owned — read-only
  reference from this map, never edited here), with its multi-source Merge
  Stage, is **the** MDM going forward — not a parallel or eventual option.
  This resolves the flag this map opened with: the GoF review's evidence
  (ADR 0007, `edgar_warehouse/mdm/database.py`'s legacy
  `mdm_change_log`/`mdm_relationship_instance`) targets a schema that is
  going away. Every decision on this map, from here on, targets Clean MDM's
  `mdm_v2` (`edgar_warehouse/mdm/clean/`), not legacy `edgar_warehouse/mdm/`.
  Ticket 01 is revised accordingly (see below) before its round-1 answer is
  taken. Not yet propagated to the parent
  [MDM Enrichment Program](../mdm-enrichment-program/map.md) or
  [GLEIF MDM enrichment evidence](../gleif-company-augmentation/map.md)
  maps' own resolved tickets — flagged there as a pointer, not rewritten,
  since re-auditing 16+28 already-resolved tickets against this constraint
  is its own piece of work, not implied by this map alone.
- Skills: `/grilling`, `/domain-modeling`, `/wayfinder`, per the parent
  program's own Notes.
- Every session uses `/grilling` and `/domain-modeling`, per the parent
  program's convention.

## Decisions so far

- [Decide where the persistent root run and phase-attempt model live](issues/01-decide-root-run-location.md)
  — shared control schema, realized as the **existing** `bookkeeping`
  (root `pipeline_run`) and `change_ledger` (`source_*` evidence lineage)
  databases, unchanged. GLEIF becomes new `command_name`/`source_family`
  values, not new tables. Consumer-facing concepts (candidate, stewardship
  decision, accepted binding, checkpoint) don't fit this acquisition-side
  shape and are ticket 05's to place.
- [Decide the GLEIF publication-family taxonomy for the shared foundation](issues/02-decide-gleif-publication-family-taxonomy.md)
  — Level 1 + Relationship Records + Reporting Exceptions as one Golden
  Copy publication family; one independent publication family per
  identifier mapping (ISIN, OpenCorporates, BIC, MIC, QCC, GEM, deferred
  CIQ), generalizing the GLEIF Company map's own tickets 07/09/11.
- [Decide delta continuity proof fields and the recovery-order algorithm](issues/03-decide-delta-continuity-and-recovery-order.md)
  — generalized verbatim from GLEIF Company ticket 14: per-family
  continuity proof, smallest-covering-delta-first recovery, full
  reconciliation only for the family that fails continuity.
- [Decide S3 path templates and Snowflake native-pull manifests](issues/04-decide-s3-path-and-snowflake-manifest-conventions.md)
  — reuse `dataset_path_catalog.py` and the existing bootstrap-SQL
  native-pull pattern; add one manifest artifact at the publication level,
  above today's per-artifact catalog rows.
- [Define the publication-aggregate schema (table names, keys, FKs)](issues/05-define-publication-aggregate-schema.md)
  — **no new tables anywhere.** A publication is *derived* from existing
  `change_ledger.source_revision` rows sharing `(source_family,
  source_native_revision)` (manifest file included); "complete" is a
  read-time precondition, not stored status. Five of the GoF review's seven
  records already exist as Clean MDM's tables; the consumer candidate is the
  pre-merge staging proposal already handed over; the checkpoint key needs a
  per-family amendment, handed to Codex as a proposal (ticket 08). There is
  one MDM and one set of MDM tables: the spec points at Clean MDM's, cites
  the defining migration, and never restates them.
- [Define the exact transaction boundary between accepted decision, MDM projection, and checkpoint advancement](issues/06-define-consumer-checkpoint-transaction-boundary.md)
  — two transactions, fixed order, nothing spans databases: capture commits
  Logical Source Revisions in `change_ledger`; the consumer checks
  publication completeness against those immutable rows; then one
  `commit_batch` call (Clean MDM's own boundary, adopted verbatim) writes
  decision + projection + Commit Evidence + Checkpoint + publication intents
  or nothing, with the consumed publication recorded in the checkpoint row.
  Bookkeeping observes afterward.

## Not yet specified

- Generic legal-entity registry representation for accepted records that
  don't justify a dedicated domain table (workstream 00's own bullet) — may
  already be substantially answered by the parent program's
  [ticket 12](../mdm-enrichment-program/issues/12-route-international-organizations-through-common-entity.md);
  revisit once ticket 05 is resolved rather than re-opening it blind.

## Out of scope

- Any implementation, schema migration, or runtime change — per this
  workstream's own "Status: planned" and the GoF review's explicit
  "not ready for schema migration or runtime implementation" conclusion.
- Domain meaning, survivorship priority, accepted relationship semantics, or
  release approval for any individual consumer (Company, Security, Fund,
  etc.) — owned by each consumer's own spec, per the parent program's
  spec-index.
- Re-deciding anything already locked in
  [GLEIF MDM enrichment evidence](../gleif-company-augmentation/map.md)'s 16
  resolved tickets — this map generalizes those decisions to the shared
  foundation, it doesn't re-litigate them.
