# Source readiness and configuration-driven mastering

Status: design interview complete and confirmed by the operator; implementation
not started. This is separate from shared PostgreSQL initialization PR #1035.

Operator request: another grill-with-docs session covering (1) synchronization
and dependency checks before Company, Person and Security source processing and
(2) whether every source can run through reading, mastering and merging using
the generic engine and configuration alone. Ask one question at a time.

- [x] Create a fresh branch/worktree from origin/main and preserve other active work. Branch `codex/source-readiness-grill-20261017`, base `48ca68c63`; no edits to another workstream (2026-10-17 07:26 ET).
- [x] Audit every configured source and the actual reading, preparation, merge, verification and Journal paths. Read-only code/configuration audit covers nine sources and thirteen contracts; none meets the full common-command target. Evidence and per-source gaps are in `docs/specs/source-readiness.md`; no behavior tests or shared-store writes performed (2026-10-17 07:29 ET).
- [x] Resolve the first dependency question. Operator chose to block required inputs while independent entity records load and unresolved relationships wait; recorded in `docs/specs/source-readiness.md`, consistent with the existing Security Identity definition (2026-10-17 07:26 ET).
- [x] Resolve synchronization/version semantics and the common execution boundary. Operator chose original versions throughout a run/resume, one common configuration-driven command, and automatic execution of declared approved local dependencies before freezing consumer inputs; documented exact choices (2026-10-17 07:29 ET).
- [x] Capture the confirmed requirements and evidence in `docs/specs/source-readiness.md`. Existing business terms remain valid; no generic implementation vocabulary added to CONTEXT.md. Static audit distinguished from behavior proof (2026-10-17 07:29 ET).
- [x] Confirm shared understanding. Operator answered "Yes, that captures the design"; related gaps mapped to existing tickets 71, 79 and 80, with mapping-version synchronization called out separately (2026-10-17 07:29 ET).
- [x] Learning → skill: none changed. The data-platform skill already describes common source workers, Python orchestration and pinned frozen runtimes; this interview records unmet runtime requirements and a source readiness audit, without claiming those gaps are implemented (2026-10-17 07:29 ET).

## Existing domain constraint

`CONTEXT.md` defines Security Identity as able to exist before its issuer is
known. A required upstream data input and an unresolved relationship endpoint
must therefore be considered separately in the interview; do not introduce a
blanket Company-before-Security condition by implication.

## Decision tree

1. Dependency policy: required approved inputs block affected work; unresolved
   relationship endpoints wait without blocking independent entity facts.
   **Confirmed by the operator, 2026-10-17.**
2. Synchronization: retain original required versions throughout completion or
   resume; newer runs use newer versions and invalidate affected Journal selections.
3. Configuration-driven execution: one common command and source configuration;
   reusable engine functions allowed, separate source preparation commands excluded.
4. Local dependencies: execute declared approved dependencies from available
   captures first, then freeze consumer inputs; missing evidence/configuration blocks.
5. Readiness proof: static audit is documented; affected per-source behavior
   qualification remains implementation work. **Do not call configured sources ready.**

## Related shipped work

The shared initialization/load-sequence work is on
`codex/full-initial-daily-load-20261016`. Its authoritative guides are
`docs/local-agent-testing.md` and `docs/initial-and-daily-source-load.md` on that
branch. It does not implement the readiness gate proposed in this interview.
Full MDM loading remains deferred for the source registration and target gaps.
