# Codex Company pickup — enrichment handoff reconciliation

2026-09-20. Rebased `codex/sec-gleif-company` onto `origin/main` `dc55bf1d`.
Preserved the assessment implementation as `f3f924a9` (pre-rebase `cf6b34f1`).
Primary/Claude/Grok checkouts were not modified.

Read [Claude's Company handoff](2026-09-19-claude-to-codex-mdm-enrichment-specs.md),
[shared foundation](../../docs/specs/mdm-enrichment/shared-foundation.md),
[Company spec](../gleif-company-augmentation/spec.md), both proposals and the
actual source/merge/checkpoint SQL. The handoff supplies planning, not a loader.

## Proposal dispositions and implementation ownership

- Pre-merge candidate persistence: **adapted and implemented**, Company Q13
  accepted. Migration 028 retains every binding/consolidation proposal, including
  automatic proposals, with no added manual approval. Candidate assessments are
  advisory; the existing master transaction remains authoritative.
- Per-family checkpoint: **accepted with historical compatibility**. Use the
  existing checkpoint table with `(consumer, source_family, publication_family)`.
  Keep old rows explicitly unscoped; never guess family or proof from encoded
  consumer strings. Store the consumed publication reference and proof on the
  cursor and immutable batch effects; there is no cross-database foreign key.
  [Ticket 10](../clean-mdm/issues/10-build-family-checkpoints.md) owns migration,
  Merge Stage integration and PostgreSQL proof of independent fencing.
- Continuity field definitions: **adopt `mdm_v2.dataset.body`**, the existing
  immutable dataset contract. This is configuration metadata, not another
  registry, table or activation switch. The source adapter must validate the
  declared proof and immutable acquisition inventory before a consume transaction.
  Persisting a supplied proof is not itself verification of source completeness.
- Required-family readiness: source-side completeness is checked from immutable
  acquisition evidence before the transaction. The master commit validates its
  own frozen family cursor/metadata atomically. Do not use a runtime boolean
  "complete" to substitute for that source verification.

## Differences requiring companion spec corrections

These corrections are recorded here instead of editing Claude's planning surface.

| Handoff/spec statement | Current controlling decision or code |
| --- | --- |
| Candidate persistence still awaiting review | Company Q13 is accepted; migration 028 and its recovery tests implement the shared foundation |
| Tier B/C always require human approval | Company Q4/Q5 require qualified fuzzy binding with corroboration and separate consolidation authority; unqualified rules remain disabled |
| Comparable field disagreements require manual disposition | Q8 selects deterministically under field authority, retaining disagreement and provenance |
| All ambiguous matches block completion | Q6/Q12 allow audited match deferrals with SEC publication; malformed source and mandatory receipts remain blocking |
| A failed bind is reversed with `revoke` | Current identity replay cannot revoke a bind; Q9's suspension/replay contract needs implementation. Do not issue unsupported decisions |
| Reversal restores checkpoints / activates a prior generation | Current reversal replays retained evidence into a new committed generation and advancing checkpoint; history is never rewound |
| First delivery is only the 1,000-company research cohort | That remains research/tracer evidence. Q3/Q12 require the frozen tracked eligible Company scope, including eligible inactive Companies |
| Golden Copy groups L1/RR/REPEX, but another paragraph says L1 independent | Foundation ticket 02 explicitly records operator acceptance of the coordinated family on 2026-09-19. That later decision supersedes the older split |
| Every publication family equals one dataset code | Dataset and publication family are distinct. Three GLEIF datasets can share one coordinated Golden Copy family; mappings remain independent |

The 308 seed links still require revalidation and do not establish independent
automatic-rule qualification. Company binding and consolidation retain their
separate ≥99.9% precision / one-sided 95% confidence gates and hard vetoes.
The Person-only 99% proposal from the 2026-09-20 handoff does not change Company
policy and is queued for the later Person workstream.

## Next execution order

1. Finish per-family cursor migration and compatibility/recovery tests.
2. Implement the immutable publication-inventory verifier and versioned continuity
   evaluation, proving a source-only offline fixture with zero domain outputs.
3. Implement GLEIF normalization/routing and pinned Company inputs, then candidate
   generation/qualification, link correction and audited match dispositions.
4. Prove the complete Company milestone before other entity consumers.

No source activation, persistent local schema migration, legacy deletion,
production rollout or hosted cutover is implied by this pickup.
