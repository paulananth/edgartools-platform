# Persistent local stores for agent testing

Status: infrastructure implemented and merged in PR #1028; captured Company financial loading remains separate work.

## Scope

The operator agreed to persistent local PostgreSQL 16 environments before Snowflake: a baseline, isolated agent environments and a shared integration environment. Each environment holds MDM, RDM, silver, Rules, Bookkeeping and Change Journal. Reuse the implemented stores and their migrations. Preserve BIGINT/64-bit long guidance and exact source numbers. No provider requests, production changes, MDM matching/merge-rule changes or hosted cutover are included.

Requested method: improve-codebase-architecture, with documentation updates and one operator question at a time.

## Parts

- [x] Inspect current main, domain terms, relevant ADRs, local provisioning and test fixtures; review history with the GoF method (main fc4e3920, independent read-only exploration and history check; 2026-10-16 16:03 ET).
- [x] Produce a temporary HTML architecture report naming evidence-backed opportunities and a top recommendation (three cards, six before/after diagrams, structural checks and desktop open request accepted; 2026-10-16 16:03 ET).
- [x] Select Company-first baseline scope with approved local captures and invented edge-case fixtures (operator reply “A”, interpreted as the first/recommended choice in the preceding question; 2026-10-16 16:06 ET).
- [x] Select automatic baseline promotion after verification, without per-baseline operator approval (operator reply “B, why do i need to approve, can we add rules to the skills because everything is agent driven”; 2026-10-16 16:14 ET).
- [x] Publish the requested skill policy separately (draft PR #1021, seven gates and setup pointer; documentation checks passed, CI running; 2026-10-16 16:14 ET).
- [x] Settle local execution policy: Company-first, automatic verified baseline updates, independent agent copies, existing Docker runtime and ordinary PostgreSQL backup/restore (operator asks no intermediate approvals and KISS; 2026-10-16 16:26 ET).
- [x] Confirm implementation and documentation scope: one local lifecycle script, existing migrations, real isolation/persistence/restore proof, README and operator/agent guide; no new promotion framework (operator “as long as you are not overrighting each other ... kiss do not over engineer”; 2026-10-16 16:26 ET).
- [x] Implement the approved local environment module, reusing existing stores and migrations (one script, real six-store startup, file locks, ordinary dump/restore; 2026-10-16 19:06 ET).
- [x] Verify independent environments, restricted roles, persistence, repeat provisioning and backup/restore (11 affected tests passed with testmon in 44.49 seconds; three invented Companies, RDM row, lookup-linked silver row and exact integer beyond binary64; 2026-10-16 19:06 ET).
- [x] Update README and local testing guide with diagrams and recovery instructions (new link, balanced fences and implemented command names verified; 2026-10-16 19:06 ET).
- [x] Review Standards, Spec and GoF (independent Standards clean; Spec and GoF final rechecks clean after two fixes; 2026-10-16 19:12 ET).
- [x] Publish the implementation PR and verify CI before landing (PR #1028, all six checks passed at 1fd931a4, squash merge d71b64a3 verified; 2026-10-16 19:23 ET).

## Decisions

- PostgreSQL 16 remains the local target. PlanetScale Metal was researched as a later hosted option; no hosted provisioning or PostgreSQL major-version upgrade was approved.
- Permanent means test/proving state can survive between sessions; it does not approve a production deployment on this machine.
- Baseline scope (2026-10-16 16:06 ET): operator replied “A” to the Company-first versus all-captured-sources question. Record Company first, combining approved local captures with invented edge-case fixtures (the earlier baseline A). The environment supports all six stores from the start; broader source qualification follows. This does not approve pending Company financials profiling findings, new matching rules or source activation.
- Baseline promotion (2026-10-16 16:14 ET): operator selected B and requested agent-driven skill rules. Candidate qualification, six-store verification, restored-baseline proof, evidence binding, atomic promotion and pinned existing environments are defined in draft skill-policy PR #1021. The later implementation is merged in PR #1028.
- Autonomy: operator permits no intermediate approvals provided agents do not overwrite one another. Proceed within this assigned local task; stop for an actual overlap or an unclear scope change. Do not invent operator approval records or expand to production/provider work.
- Use the configured Docker runtime (currently OrbStack), independent named volumes, private environment files and PostgreSQL dump/restore. Reuse migrations; no framework, new database engine or dashboard. The GoF consult keeps the existing engines and disposable fixture unchanged.

## Architecture evidence

- The startup script fixes one container, volume and port and prints complete connection addresses. A permanent multi-agent environment needs explicit resource ownership and secret-safe status.
- The existing bootstrap provisions three control stores; MDM, RDM and silver initialization remain separate. RDM and Rules require exact database names, which independent PostgreSQL containers preserve.
- A silver acceptance fixture with a persistent administrator override force-drops a shared MDM template. Keep destructive acceptance targets apart from persistent proving and the approved baseline.
- Recommendation: one local environment lifecycle module covering identity, six-store provisioning and test ownership, reusing the store migrations and existing disposable PostgreSQL adapter. Do not add a GoF class hierarchy.
- ADR 0013 requires retained identity registry/history for exact-ID replay. Source-only reconstruction is not an exact-ID backup. ADR 0016 preserves independent MDM and silver mappings.
- This initial architecture evidence came from code/history inspection before implementation; the later behavioral proof and empty local environment are recorded above.

## Interview frontier

Interview complete for the assigned local infrastructure. Record new facts and resolve routine engineering choices without further approval prompts. An actual overlap or missing necessary information is a reason to ask; no production or provider scope expansion is included.

## Implementation limits

The persistent environment currently provides all six migrated stores. The qualification test uses invented records only. Captured Company financial facts are not silently loaded through an unqualified reader; reader and financial-table work remain in the existing Company financials tickets. A baseline created from an empty store is an empty starting copy, not proof of that business pipeline.

A backup made with the final script was restored and promoted successfully for the persistent six-store environment; it contains no captured business data (2026-10-16 19:23 ET).

## Final review fixes

- [x] Preserve PostgreSQL ACLs so restored silver runtime connections can read and land registered tables (restored-runtime SELECT, INSERT and DELETE verified; 2026-10-16 19:10 ET).
- [x] Recover interrupted backup login fencing on startup from a private atomic record (forced NOLOGIN + restart recovery verified; 2026-10-16 19:10 ET).
- [x] Recheck affected behavior after the fixes (11 tests passed with testmon in 48.76 seconds; 2026-10-16 19:10 ET).

Standards review found no issues. Independent Spec and GoF rechecks passed after both fixes at dbcea8a9; reviews were read-only, and the 11-test behavior run was executed separately (2026-10-16 19:12 ET).

- [x] Learning → skill: data-platform/LOCAL-TESTING.md defines automatic work with independent copies and ordinary backups (separate PR #1021 merged after all six checks passed; 2026-10-16 19:06 ET).
