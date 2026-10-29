# Retire PostgreSQL business routines and caller paths

Type: task
Status: resolved
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: none — 07 merged in #1178; skill learning #1179 merged

## Current closeout — 2026-10-28 20:12 ET

PRs #1180 / 1190 / 1191 are merged; 21 final-head checks pass on each PR; current owner-retirement and installed evidence remain qualified. Current qualification is 160 installed cases per engine, two configured kinds and all 18 families at #1210. [Closeout evidence](../assets/completion-evidence.json) records the verified heads and limits. Historical checkpoints below retain their original dates.

## Question

Can the active PostgreSQL business implementation be removed after the shared caller is qualified?

Claimed by Codex on `codex/mdm-retire-business-routines-20261026`, fresh from main `43588ae7` (2026-10-26 07:46 ET). The restarted MDM check on #1178 also completed successfully before this claim. No open PRs at claim.

Continued by Codex on `codex/mdm-retire-callers-20261027`, fresh from main `790a2ca6` (2026-10-26 20:10 ET). PR #1180 is merged. The caller cleanup starts after a prospective overlap check passed for all 13 initially inventoried caller files.

## Parts

- [x] Add a new owner migration retiring the inventoried superseded business routines; preserve historical migration files and required storage enforcement — 2026-10-26 07:56 ET: migration 028 removes 34 routines, retains two integrity guards; three real-engine retirement cases pass per engine, including rollback and retained-state checks. Final CI remains a separate gate below.
- [x] Delete superseded active Python SQL caller paths, policy branches and duplicated database calculation tests; retain transactions, uniqueness, grants, migrations, concurrency, authority and recovery integration checks — 2026-10-26 21:06 ET: runtime AST regression, 1,072 affected unit/MDM checks, real PostgreSQL source-chain checks and both-engine targeted storage checks pass; final installed/CI gate remains below.
- [x] Account for every retired integration calculation test and retain the selected-engine storage, migration, rights, concurrency and recovery checks. — 2026-10-27 06:51 ET: 254 functions in 33 files retain per-test dispositions and maintained suite references; storage, fault, concurrency and recovery suites remain; 28 targeted installed cases pass across both engines.
- [x] Verify a populated PostgreSQL upgrade preserves durable state and the normal caller no longer invokes retired routines; repeat normal MySQL parity and unchanged replay. — 2026-10-27 06:51 ET: real populated worker upgrades, interrupted installed upgrades and replay pass on both engines; the runtime AST refuses all 34 retired calls.
- [x] Publish before/after active-code and routine counts separately from historical SQL; do not count retained historical migrations as unfinished active business logic. — 2026-10-27 06:51 ET: 6415 → 5418 physical lines in 23 changed runtime modules; counts and per-file measurements published; 001–027 remain unchanged.
- [x] Qualify the committed retirement revision through the required independently installed workflow and all CI checks — 2026-10-27 07:23 ET: [CI run 40491799251](https://github.com/paulananth/edgartools-platform/actions/runs/40491799251), all 21 checks green at `00528468`; 328 installed cases (164 per engine), both configured kinds, all 18 families, equal pins and cleanup verified; the installed merge revision contains the PR head.
- [x] Complete governed Proving Run counts and source-chain reader cleanup — 2026-10-26 21:06 ET: normal reader inspection passes both configured kinds on both engines, including deferred counts and byte-hash replay; PostgreSQL source/Silver and independent worker/verifier checks pass; operator assigned `edgar_warehouse/rules/proving.py` and `tests/integration/test_openfigi_security.py` to Codex after the overlap report (2026-10-26 20:36 ET). The archived Claude branch remains untouched.
- [x] Qualify narrow configuration-registration authority added after the local bootstrap exposed missing governance access; keep master saves, gate writes and configuration approval duties separate. — 2026-10-27 06:51 ET: three PostgreSQL registrar rights/rollback/drift checks include policy/mapping/schema approval; real separate-role bootstrap and restore pass; six PostgreSQL and four MySQL regression checks pass, including concurrent registration.
- [x] Retain explicit offline answers before deleting the historical implementation oracle — 2026-10-27 06:51 ET: 64 field/identity answer pairs agree before removal; 128 individual changed answers are rejected; 84 targeted checks pass.
- [x] Resolve the newly reported execution-file overlap before publishing closeout — 2026-10-27 07:30 ET: operator explicitly instructed Codex to take over and complete retirement; only this branch is published, with Claude ticket 138 work preserved.
- [x] Learning → skill: update its owning skill on a separate branch/PR, or record none. — 2026-10-27 06:51 ET: separate PR #1191 updates mdm-engineering owner-installation guidance, current-read/concurrency qualification and retired reader/test pointers; both changed references pass genericity.

## Acceptance evidence

No normal caller reaches retired PostgreSQL business routines; both workflows still pass and the database retains authoritative atomic enforcement.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.

## Current implementation

[Governed routine retirement evidence and counts](../assets/routine-retirement.md) records the first retirement slice. [Caller retirement evidence](../assets/caller-retirement.md) records implementation in PR #1190 and the bounded installed checks. All implementation and qualification parts are verified. PR #1190 is ready for the separate named merge decision; source activation and hosted conversion remain outside this ticket.
