# 22 — Migrate company-facts snapshots

**What to build:** Carry authoritative company-facts snapshots through the
registered acquisition path and publish only their verified affected scopes to
Silver.

**Blocked by:** 17 — Make Bronze capture retry-safe and recoverable; 20 —
Version and activate the Acquisition Universe

**Status:** ready-for-agent

- [ ] The family Strategy defines the CIK-scoped logical identity, full-snapshot
  completeness proof, conditional fetch policy, and required producers.
- [ ] Scope Completion includes the authoritative member count and ordered
  digest, including a valid complete-empty scope.
- [ ] Missing, partial, or failed snapshots cannot retire prior facts or become
  the current Silver authority.
- [ ] Changed, unchanged, reinterpreted, replayed, and retired facts produce
  deterministic verified outcomes with bounded work evidence.
- [ ] No direct company-facts adapter caller bypasses the gated Facade.
