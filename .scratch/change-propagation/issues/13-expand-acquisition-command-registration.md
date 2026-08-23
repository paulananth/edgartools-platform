# 13 — Expand acquisition command registration

**What to build:** Introduce a behavior-preserving Command-style registration
boundary for acquisition operations. Each migrated command binds execution,
scope resolution, and planned writes as one unit, while commands not yet
migrated continue through the existing dispatch path.

**Blocked by:** None — can start immediately

**Status:** resolved

- [x] One existing acquisition command runs through a single registration that
  supplies execution, scope resolution, and planned-write behavior.
- [x] Unregistered commands continue through the existing behavior without a
  broad orchestrator rewrite.
- [x] Registration validation fails fast when any required behavior is absent
  or duplicated.
- [x] Characterization tests prove the migrated command preserves its current
  externally observable scope and output behavior.
- [x] Runtime import and command-discovery tests prevent execution and scope
  resolution from drifting apart again.
