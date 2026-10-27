# Retire PostgreSQL business routines and caller paths

Type: task
Status: claimed
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: none — 07 merged in #1178; skill learning #1179 merged

## Question

Can the active PostgreSQL business implementation be removed after the shared caller is qualified?

Claimed by Codex on `codex/mdm-retire-business-routines-20261026`, fresh from main `43588ae7` (2026-10-26 07:46 ET). The restarted MDM check on #1178 also completed successfully before this claim. No open PRs at claim.

Continued by Codex on `codex/mdm-retire-callers-20261027`, fresh from main `790a2ca6` (2026-10-26 20:10 ET). PR #1180 is merged. The caller cleanup starts after a prospective overlap check passed for all 13 initially inventoried caller files.

## Parts

- [x] Add a new owner migration retiring the inventoried superseded business routines; preserve historical migration files and required storage enforcement — 2026-10-26 07:56 ET: migration 028 removes 34 routines, retains two integrity guards; three real-engine retirement cases pass per engine, including rollback and retained-state checks. Final CI remains a separate gate below.
- [x] Delete superseded active Python SQL caller paths, policy branches and duplicated database calculation tests; retain transactions, uniqueness, grants, migrations, concurrency, authority and recovery integration checks — 2026-10-26 21:06 ET: runtime AST regression, 1,072 affected unit/MDM checks, real PostgreSQL source-chain checks and both-engine targeted storage checks pass; final installed/CI gate remains below.
- [ ] Account for every retired integration calculation test and retain the selected-engine storage, migration, rights, concurrency and recovery checks.
- [ ] Verify a populated PostgreSQL upgrade preserves durable state and the normal caller no longer invokes retired routines; repeat normal MySQL parity and unchanged replay.
- [ ] Publish before/after active-code and routine counts separately from historical SQL; do not count retained historical migrations as unfinished active business logic.
- [ ] Qualify the committed retirement revision through the required independently installed workflow and all CI checks.
- [x] Complete governed Proving Run counts and source-chain reader cleanup — 2026-10-26 21:06 ET: normal reader inspection passes both configured kinds on both engines, including deferred counts and byte-hash replay; PostgreSQL source/Silver and independent worker/verifier checks pass; operator assigned `edgar_warehouse/rules/proving.py` and `tests/integration/test_openfigi_security.py` to Codex after the overlap report (2026-10-26 20:36 ET). The archived Claude branch remains untouched.
- [ ] Qualify narrow configuration-registration authority added after the local bootstrap exposed missing governance access; keep master saves, gate writes and configuration approval duties separate.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

## Acceptance evidence

No normal caller reaches retired PostgreSQL business routines; both workflows still pass and the database retains authoritative atomic enforcement.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.

## Current implementation

[Governed routine retirement evidence and counts](../assets/routine-retirement.md) records the first retirement slice. Python fallback removal and test retirement remain incomplete; this change does not claim the full ticket is resolved.
