# Connect master reads and operator commands

Type: task
Status: claimed
Assignee: Codex
Claimed: 2026-10-24 09:55 ET
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 04

## Question

Can installed consumers and operators use normal engine-selected MDM read and inspection paths?

## Parts

- [ ] Finish current/history/detail/relationship/context reads and real master-identifier lookup used by Silver.
- [ ] Connect counts, connectivity, health, inspection and supported publication commands to selected-engine storage; preserve authorization and bounded exact-key plans.
- [ ] Verify original JSON, large numbers, Unicode and opaque identifiers survive transport; keep errors and public evidence free of source values.
- [ ] Investigate the missing destination recording timestamp and bounded ordered history/page indexes before implementing historical context; preserve protocol 1–5 fingerprints if a storage extension is required.
- [ ] Qualify the normal installed consumer/context and actual Silver-facing lookup on both engines, with original provenance, aliases, historical detail boundaries and bounded plans.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

## Acceptance evidence

Normal installed reads and commands work on both engines, including the real Silver-facing lookup; helper callbacks alone do not qualify the path.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.

## Initial consult — 2026-10-24 09:55 ET

The fresh reader branch starts from current origin/main and carries prerequisite
04 commits by fast-forward; PR #1159 is still in CI, not merged. It changes no
runtime on this branch yet. Existing native readers remain the rollback path.

GoF review of consumer.py, Context and Silver MdmIds plus their histories shows
a shared transport gap, not a new merge algorithm. Keep their public contracts,
use typed selected-engine queries and reuse validated RecordReader references.
The portable path must handle every configured kind uniformly. Preserve native
PostgreSQL behavior until retirement is separately qualified.

Inspection found that the prepared batch model has generation, producer and
intent, but no destination recording timestamp. Context currently distinguishes
business --as-of from recording --as-at and returns original recorded_at.
Investigate that behavior on real prepared stores before choosing the smallest
storage extension; caller business time must not stand in for server recording
time. Current history keys support exact object/generation reads, but pages
ordered by original opaque ids and master-name search need demonstrated indexed
plans. Keep these explicit; a full-table Python filter is not an implementation.

Task 05 remains incomplete. No Context ownership is assumed: reconcile its
standing Claude ownership and live overlap before editing that command module.
Other consumer and Silver read work can progress independently.
