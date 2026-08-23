# 23 — Migrate reference catalogs

**What to build:** Carry each supported SEC reference catalog through explicit
version, completeness, acquisition, revision, and Silver lifecycle semantics.

**Blocked by:** 17 — Make Bronze capture retry-safe and recoverable; 20 —
Version and activate the Acquisition Universe

**Status:** ready-for-agent

- [ ] Each catalog Strategy defines its source scope, producer version evidence,
  completeness proof, conditional acquisition policy, and required producers.
- [ ] A complete catalog records its member count and ordered member-key digest;
  a valid zero-member catalog can complete without fabricated rows.
- [ ] Partial, unavailable, or malformed catalogs cannot emit Scope Completion
  or retire prior authoritative members.
- [ ] Replays and byte-identical observations produce no duplicate business
  mutations while retaining explicit acquisition evidence.
- [ ] Each catalog command uses a bundled acquisition handler and introduces no
  catalog-specific branching into the shared Facade.
