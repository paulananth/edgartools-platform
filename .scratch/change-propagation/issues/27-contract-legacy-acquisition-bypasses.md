# 27 — Contract legacy acquisition bypasses

**What to build:** Remove the obsolete direct acquisition and legacy dispatch
paths after every supported family has demonstrated the authoritative path,
leaving one enforceable route from decision through verified Bronze and
published processing status.

**Blocked by:** 21 — Migrate submissions snapshots and pagination; 22 — Migrate
company-facts snapshots; 23 — Migrate reference catalogs; 24 — Migrate ADV
sources; 25 — Add conflict, repair, exclusion, and evidence-import workflows

**Status:** ready-for-agent (corrected 2026-08-27). Ticket 26 removed from
this ticket's blockers — [Ticket 10](10-decide-migration-cutover-rollback.md)'s
Decision 5 found it was never a genuine prerequisite (ordinary per-family
cutover doesn't route through Ticket 26's rebuild machinery at all). Ticket
24's bullet 4 (`adv_filing` had no discovery driver) is now fully resolved,
not partial. Ticket 22 (bullets 1/4/5) and Ticket 23 (bullet 1) still carry
named partial bullets, but per this map's established convention (see
Ticket 26's own prior correction) a `resolved`-prefixed status satisfies
blocking regardless of partial detail — every listed blocker is resolved.
**Not yet reflected in this ticket's own scope, worth resolving before
starting:** Ticket 10's Decision 2 (side-by-side verification per family
before retiring its legacy call) and the newly-confirmed fact that none of
the new drivers are wired into any schedule yet (also Ticket 10) — this
ticket's bullets below predate both findings and may need a pass to
incorporate them (e.g. the actual removal work is gated per-family on
Decision 2's diff proof, not a single all-families-at-once removal).

- [ ] Architecture tests prove every approved low-level source adapter is
  reachable only through the ledger-gated Facade.
- [ ] Every required Source Family Registry entry supplies complete executable
  discovery, fetch, completeness, and required-producer policies.
- [ ] Every acquisition command binds execution, scope resolution, and planned
  writes in one validated registration; legacy acquisition dispatch is gone.
- [ ] Persisted lifecycle remains enforced by PostgreSQL constraints and a
  deterministic reducer or transition table rather than GoF State objects.
- [ ] Durable delivery remains a transactional outbox rather than Observer
  callbacks, and no unproven Template Method hierarchy is introduced.
- [ ] End-to-end and rollback evidence prove removal leaves no unsupported
  family, unauthorized network path, or partial serving state.
