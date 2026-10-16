# Persistent local stores for agent testing

Status: architecture review and operator interview; implementation has not started.

## Scope

The operator agreed to persistent local PostgreSQL 16 environments before Snowflake: a baseline, isolated agent environments and a shared integration environment. Each environment holds MDM, RDM, silver, Rules, Bookkeeping and Change Journal. Reuse the implemented stores and their migrations. Preserve BIGINT/64-bit long guidance and exact source numbers. No provider requests, production changes, MDM matching/merge-rule changes or hosted cutover are included.

Requested method: improve-codebase-architecture, with documentation updates and one operator question at a time.

## Parts

- [x] Inspect current main, domain terms, relevant ADRs, local provisioning and test fixtures; review history with the GoF method (main fc4e3920, independent read-only exploration and history check; 2026-10-16 16:03 ET).
- [x] Produce a temporary HTML architecture report naming evidence-backed opportunities and a top recommendation (three cards, six before/after diagrams, structural checks and desktop open request accepted; 2026-10-16 16:03 ET).
- [x] Select Company-first baseline scope with approved local captures and invented edge-case fixtures (operator reply “A”, interpreted as the first/recommended choice in the preceding question; 2026-10-16 16:06 ET).
- [x] Select automatic baseline promotion after verification, without per-baseline operator approval (operator reply “B, why do i need to approve, can we add rules to the skills because everything is agent driven”; 2026-10-16 16:14 ET).
- [x] Publish the requested skill policy separately (draft PR #1021, seven gates and setup pointer; documentation checks passed, CI running; 2026-10-16 16:14 ET).
- [ ] Settle baseline content, refresh, isolation, runtime, lifecycle and recovery decisions with the operator, one question at a time; record exact decisions.
- [ ] Confirm shared understanding and record the approved implementation and documentation scope.
- [ ] Implement the approved local environment module, reusing existing stores and migrations.
- [ ] Verify independent environments, restricted roles, persistence, repeat provisioning and backup/restore with affected local tests under five minutes per invocation.
- [ ] Update the project entry documentation and an executable local testing guide with diagrams and recovery instructions.
- [ ] Review Standards, Spec and GoF, publish a PR and verify CI before landing.
- [ ] Learning → skill: pending; record any reusable operational lesson in its applicable skill on a separate branch/PR, or write none.

## Decisions

- PostgreSQL 16 remains the local target. PlanetScale Metal was researched as a later hosted option; no hosted provisioning or PostgreSQL major-version upgrade was approved.
- Permanent means test/proving state can survive between sessions; it does not approve a production deployment on this machine.
- Baseline scope (2026-10-16 16:06 ET): operator replied “A” to the Company-first versus all-captured-sources question. Record Company first, combining approved local captures with invented edge-case fixtures (the earlier baseline A). The environment supports all six stores from the start; broader source qualification follows. This does not approve pending Company financials profiling findings, new matching rules or source activation.
- Baseline promotion (2026-10-16 16:14 ET): operator selected B and requested agent-driven skill rules. Candidate qualification, six-store verification, restored-baseline proof, evidence binding, atomic promotion and pinned existing environments are defined in draft skill-policy PR #1021. The lifecycle implementation remains pending.
- Broader autonomy for source findings, mappings and matching/merge-rule approval is an unresolved scope question; this ruling is not silently extended to those decisions.
- Further implementation choices remain open until the interview resolves them.

## Architecture evidence

- The startup script fixes one container, volume and port and prints complete connection addresses. A permanent multi-agent environment needs explicit resource ownership and secret-safe status.
- The existing bootstrap provisions three control stores; MDM, RDM and silver initialization remain separate. RDM and Rules require exact database names, which independent PostgreSQL containers preserve.
- A silver acceptance fixture with a persistent administrator override force-drops a shared MDM template. Keep destructive acceptance targets apart from persistent proving and the approved baseline.
- Recommendation: one local environment lifecycle module covering identity, six-store provisioning and test ownership, reusing the store migrations and existing disposable PostgreSQL adapter. Do not add a GoF class hierarchy.
- ADR 0013 requires retained identity registry/history for exact-ID replay. Source-only reconstruction is not an exact-ID backup. ADR 0016 preserves independent MDM and silver mappings.
- This evidence is code/history inspection, not behavioral proof. No runtime tests, containers, stores or source data were touched.

## Interview frontier

Ask one question per turn. Company-first baseline content is selected. Automatic baseline promotion is selected. Next settle whether agent-driven autonomy also covers source/rule approvals, then runtime, ownership of resets and backups, qualification and documentation scope. No detailed interface or new CLI command is proposed before the scope is settled.
