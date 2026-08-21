# Milestones

## v1.0 — Warehouse S3 duplicate-storage reclaim

**Shipped:** 2026-08-21
**Status:** complete
**Phases:** 1-4 complete; Phase 5 dropped
**Plans:** 4 (wayfinder `/to-tickets` 07–10; no GSD PLAN.md)
**Known deferred items at close:** 5 (see STATE.md Deferred Items)

### Delivered

Prod warehouse bucket leak-seal and VersionId reclaim of leftover duplicates, without touching current Canonical Silver.

### Key accomplishments

1. Joined Live Key lifecycle: `warehouse/silverstage/` 3/3, `warehouse/identity_refresh/` 7/7, `warehouse/silver/` noncurrent-only 7
2. Architecture tests lock Terraform prefixes to `StorageLocation.join()`
3. Sibling reclaim tool (ADR 0004 stays staging-only)
4. One-shot reclaim: 1.71 TiB silverstage (2026-08-20) + 339.8 GiB shards/identity/gold (2026-08-21)
5. Bronze inventory: no material current-key duplicates
6. CW-01 dropped; seven-day CloudWatch floor stands

### Known Gaps

- **CW-01**: dropped, not shipped
- Remaining `warehouse/gold/` keep-set is a dual-write leftover; stop-writer + reclaim-all is a new effort

### Git

- Branch: `claude/silverstage-lifecycle` merged as PR #428 (`eb45156e`)
- Do not tag the platform repo `v1.0` for this workstream
