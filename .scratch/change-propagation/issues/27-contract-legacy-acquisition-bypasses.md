# 27 — Contract legacy acquisition bypasses

**What to build:** Remove the obsolete direct acquisition and legacy dispatch
paths after every supported family has demonstrated the authoritative path,
leaving one enforceable route from decision through verified Bronze and
published processing status.

**Blocked by:** 21 — Migrate submissions snapshots and pagination; 22 — Migrate
company-facts snapshots; 23 — Migrate reference catalogs; 24 — Migrate ADV
sources; 25 — Add conflict, repair, exclusion, and evidence-import workflows;
26 — Rebuild and activate a ledger epoch

**Status:** ready-for-agent

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
