# 18 — Materialize ordered logical source revisions

**What to build:** Convert verified Bronze captures into immutable, ordered
Logical Source Revisions and reasoned Processing Decisions without treating
transport identity or operational timestamps as business change.

**Blocked by:** 04 — Prototype the Change Propagation Run contract; 15 — Capture
one filing-artifact family through the gated Facade

**Status:** ready-for-agent

- [ ] A revision records the logical source identity, observation position,
  source-native revision, three versioned content hashes, interpretation
  versions, completeness declaration, and verified evidence lineage.
- [ ] Observation positions are monotonic per logical key but may contain gaps
  for failed, skipped, and not-modified observations.
- [ ] Processing is serialized per logical source key while unrelated keys may
  proceed concurrently.
- [ ] Changed interpretation reuses verified Bronze without downloading again;
  authenticated new source revisions with unchanged domain content record an
  explicit publication-backed `NO_IMPACT` path.
- [ ] Tests reject run identifiers, arrival times, object paths, mutable
  pointers, and ETags alone as revision identity.
