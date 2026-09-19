# Write the per-family checkpoint-key proposal for Clean MDM and hand it over

Type: task
Status: open
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
