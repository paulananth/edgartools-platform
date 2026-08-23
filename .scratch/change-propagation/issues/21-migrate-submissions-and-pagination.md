# 21 — Migrate submissions snapshots and pagination

**What to build:** Carry submissions main snapshots and every declared
pagination file through registered discovery, acquisition, completeness,
revision, and Silver-publication behavior as one source-family slice.

**Blocked by:** 17 — Make Bronze capture retry-safe and recoverable; 20 —
Version and activate the Acquisition Universe

**Status:** ready-for-agent

- [ ] The family Strategy defines the company and pagination logical keys,
  ordered inventory proof, conditional fetch behavior, and required producers.
- [ ] A main snapshot cannot declare completeness while a referenced pagination
  file is missing, deferred, failed, corrupt, or unverified.
- [ ] Company, address, former-name, and submission-file scopes remain distinct
  and retire only from a proved complete scope.
- [ ] Complete empty scopes, unchanged observations, pagination changes, and
  replay all reach explicit verified outcomes.
- [ ] The acquisition Command registration bundles execution, scope resolution,
  and planned writes without adding source-family branches to the Facade.
