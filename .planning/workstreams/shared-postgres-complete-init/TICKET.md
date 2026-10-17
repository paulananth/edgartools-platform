# Complete shared PostgreSQL initialization without silver

Operator request: fix initialization for MDM, RDM, Rules, Bookkeeping and the
Change Journal, excluding silver, then reinitialize the existing shared server.
Reinitialization applies migrations and access setup; existing data is retained.

- [x] GoF consult and current-state/ownership check. Single-change history supports keeping the existing facade; the shared server has no other client connections and retains its creating worktree (2026-10-16 20:40 ET).
- [x] Implement five-store initialization, execution roles, private connection files and the MDM destination guard; preserve older backups. Core-only defaults, optional silver and legacy six-store selection are covered by PostgreSQL acceptance (2026-10-16 20:40 ET).
- [x] Verify meaningful role separation, guard behavior, reinitialization and backup/restore on disposable PostgreSQL 16 in affected tests under five minutes. Final testmon run: 16 passed, 1 deselected, 26.80 s; the unchanged six-store acceptance also passed in the preceding 57.69 s run. All 17 affected cases passed across those runs (2026-10-16 20:40 ET).
- [x] Update initialization documentation and review Standards, Spec and GoF. README and local guide explain the five-store default and duty-specific connections; CLI examples/shell blocks and whitespace checked; overlap guard passed (2026-10-16 20:40 ET).
- [ ] Rerun initialization on the owned shared server and verify all five stores, role access and unchanged existing contents, including silver.
- [ ] Learning → skill.

## GoF consult

`local-test-stores.py` has one committed change (#1028), so there is no
repeated-change evidence warranting a design-pattern refactor. Keep LocalStores
as the existing facade; use named store selection and small role/setup helpers
to remove positional migration coupling. No new framework or class hierarchy.

## Standards

Fresh branch/worktree; no matching rules or applied migration files changed.
Real PostgreSQL tests use disposable targets and clean them on every exit.
Connection files are private, worker/verifier authority is separate, all added
roles lack superuser/database/role-creation powers, and ordinary MDM writes
remain through its functions. Local tests stay below five minutes per run.

## Spec

Default initialization provisions MDM, RDM, Rules, Bookkeeping and the Change
Journal. It omits silver migrations and connections while preserving any
existing silver database. Backups include all previously managed stores;
both five-store and legacy six-store restore are tested. Initialization
creates no source approval, activation or captured source records.

## GoF

Post-change review using gof-refactor-reviewer: no pattern refactor warranted.
Store-to-migration selection is explicit; the existing lifecycle facade owns
provisioning, duty connections and recovery. The tests exercise real authority
and recovery behavior instead of reproducing the implementation.
