# 27 — Contract legacy acquisition bypasses

**What to build:** Remove the obsolete direct acquisition and legacy dispatch
paths after every supported family has demonstrated the authoritative path,
leaving one enforceable route from decision through verified Bronze and
published processing status.

**Blocked by:** 21 — Migrate submissions snapshots and pagination; 22 — Migrate
company-facts snapshots; 23 — Migrate reference catalogs; 24 — Migrate ADV
sources; 25 — Add conflict, repair, exclusion, and evidence-import workflows;
46 — Wire `filing_artifact`'s gated driver into `daily_incremental`

**Status:** blocked on Ticket 46 (added 2026-08-27 — see below). Ticket 26 removed from
this ticket's blockers — [Ticket 10](10-decide-migration-cutover-rollback.md)'s
Decision 5 found it was never a genuine prerequisite (ordinary per-family
cutover doesn't route through Ticket 26's rebuild machinery at all). Ticket
24's bullet 4 (`adv_filing` had no discovery driver) is now fully resolved,
not partial. Ticket 22 (bullets 1/4/5) and Ticket 23 (bullet 1) still carry
named partial bullets, but per this map's established convention (see
Ticket 26's own prior correction) a `resolved`-prefixed status satisfies
blocking regardless of partial detail — every listed blocker is resolved.
**Corrected again 2026-08-27:** the "worth resolving before starting" note
above has been resolved by actually starting — live investigation into how
to wire `filing_artifact` into a real schedule (Ticket 10's Decision 4)
found the mechanism substantially more delicate than either this ticket or
Ticket 10 assumed (`daily_incremental`'s Step Function definition has
SEC-fetch lease acquisition/release, refresh-mode branching, and deferred-
execution handling — the same state machine behind two prior documented
incidents in CLAUDE.md). That concrete first slice — wiring one family's
driver into one schedule, the prerequisite for this ticket's own removal
work to have any real evidence to act on — is split out as its own ticket:
[46 — Wire `filing_artifact`'s gated driver into `daily_incremental`](46-wire-filing-artifact-into-daily-incremental.md).
This ticket (27) now additionally depends on 46's outcome for its own
bullets to be actionable — its removal-evidence bullets cannot be attempted
for any family until that family has been through a real Decision-2
side-by-side window, and none has yet.

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
