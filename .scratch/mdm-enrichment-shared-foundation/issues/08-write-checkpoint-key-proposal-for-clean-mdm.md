# Write the per-family checkpoint-key proposal for Clean MDM and hand it over

Type: task
Status: resolved
Blocked by: none (graduated from ticket 05, Q1)

## Question

Nothing to decide — [ticket 05](05-define-publication-aggregate-schema.md)
Q1 locked it: this map specifies the checkpoint key the shared foundation
needs, and hands it to Codex/Grok as a proposal. It does not edit Clean
MDM's files.

Write the proposal, in the same shape and location as the
[pre-merge staging proposal](../../clean-mdm-premerge-staging-proposal/map.md),
plus a `.scratch/handover/<date>-claude-to-codex-<topic>.md` pointer
following `.scratch/handover/2026-09-19-claude-to-codex-mdm-premerge-proposal.md`.

Content the proposal must carry:

- **What exists**: `mdm_v2.checkpoint (consumer PRIMARY KEY, position bigint,
  batch_id)` in migration 023, written by `commit_batch_core`'s
  `INSERT ... ON CONFLICT(consumer) DO UPDATE SET position=...`.
- **What the foundation needs**: key `(consumer, source_family,
  publication_family)`; committed publication identity (the
  `(source_family, source_native_revision)` pair from ticket 05, since a
  publication is derived, not a row); pending cursor; continuity proof
  (ticket 03's per-family field set); `batch_id`/`run_id` lineage as today.
- **Why**: [ticket 02](02-decide-gleif-publication-family-taxonomy.md)'s
  ~8 independent publication families and [ticket 03](03-decide-delta-continuity-and-recovery-order.md)'s
  "never advance a sibling family's checkpoint" cannot be expressed with one
  scalar position per consumer. Clean MDM's own `docs/specs/clean-mdm/recovery.md`
  line 20 already describes the checkpoint as carrying "family/epoch and
  source position" — the DDL lags their spec; this proposal asks them to
  close that gap, not to change direction.
- **What it is not**: no edit to any Clean MDM file, no reopened Q1–Q16
  policy, no implementation.

Resolved when the proposal map and the handover pointer are committed and
the operator has been told (as before) that the next Codex session must be
pointed at the handover file manually.

## Answer

Done, 2026-09-19:

- Proposal map: [`.scratch/clean-mdm-checkpoint-key-proposal/map.md`](../../clean-mdm-checkpoint-key-proposal/map.md)
- Proposal body: [`issues/01-write-checkpoint-key-proposal.md`](../../clean-mdm-checkpoint-key-proposal/issues/01-write-checkpoint-key-proposal.md)
  — current DDL and fence quoted from `023_clean_mdm.sql`; the foundation's
  need (tickets 02/03/06); three pieces of evidence from Clean MDM's own
  files that this is their stated direction (`recovery.md` line 20,
  `source-evidence.md`'s "each mapping has its own checkpoint," and
  `company_source.py` lines 195–199 already minting a per-batch consumer
  string to work around the narrow key); proposed DDL widening the key to
  `(consumer, source_family, publication_family)` and adding
  `committed_publication` + `continuity_proof`; four open questions left
  to Clean MDM.
- Handover pointer: [`.scratch/handover/2026-09-19-claude-to-codex-mdm-checkpoint-key-proposal.md`](../../handover/2026-09-19-claude-to-codex-mdm-checkpoint-key-proposal.md),
  which also reminds Codex the earlier pre-merge staging proposal is still
  awaiting review and that the two together complete the GoF 7-record
  contract on their side.

Nothing under `.scratch/clean-mdm/`, `docs/specs/clean-mdm/`, or
`edgar_warehouse/mdm/clean/` was touched. The operator must point the next
Codex session at the handover file manually.
