Type: task
Status: open
Blocked by: 02

**Repurposed by [Ticket 02](02-decide-write-time-fix-mechanism.md):** originally
scoped as "implement + deploy a write-time fix." Ticket 01 found the
write-time bug is a one-time historical event, already gone as a side
effect of the 2026-08-21 CRD-batching refactor (`869003da`) — 3+ weeks of
clean writes since. No code fix is needed. This ticket is now a
lightweight live-monitoring check instead.

## What to build

A periodic check (mirroring this repo's existing `mdm check-fence`
precedent — verifying a fixed assumption stays true, not re-deriving it
from scratch each time) that alerts if any MANAGES_FUND `relationship_id`
ever gets a second currently-active, non-quarantined, non-superseded row
with byte-identical `properties`/`valid_from_date`/`valid_to_date` to an
existing one. Cheap insurance against Ticket 01's unconfirmed-mechanism
gap — if this reasoning turns out wrong, this catches a regression
quickly instead of silently letting a new backlog regrow.

## Acceptance

- [ ] Check queries MDM Postgres for new post-cleanup-baseline duplicate
      groups (scoped to MANAGES_FUND only — this is not a general
      relationship-integrity monitor).
- [ ] Wired into whatever this repo's existing alerting mechanism is
      (check `mdm check-fence`'s own wiring for precedent) rather than a
      standalone script nobody runs.
- [ ] `/gof-refactor-reviewer` consulted before editing (repo hard rule).
- [ ] `/code-review` (Standards, Spec, GoF) run before PR is ready.
