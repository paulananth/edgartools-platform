# Source sequencing configuration check

Status: in progress. Scope: offline configuration checking, not source activation
or a replacement executor. Base: `06a98a189`.

Operator: implement source sequencing configuration checks; each source can be
selected independently; a delayed source can be overridden without stopping
unrelated sources. Interpret the override as an explicit deferral, never as
permission to bypass required inputs or change frozen versions.

## Parts

- [x] Inspect current main, Claude ownership and existing submission/validation interfaces — fetched main `06a98a189`, both readiness Claude sessions done, sibling worktree and guard verified; 2026-10-17 08:27 ET.
- [x] Consult GoF on the existing Rules command and Bookkeeping configuration code — code, history and skill references inspected; no class hierarchy justified; 2026-10-17 08:27 ET.
- [x] Implement and test the public configuration-check interface: graph validation, independent selection, required dependencies, preferred order and explicit deferrals — command behavior tests passed; 2026-10-17 08:27 ET.
- [x] Inventory all committed source configurations without claiming runtime readiness — nine-source inventory equality and nine independent selections tested; three existing targets, six explicitly missing; 2026-10-17 08:27 ET.
- [x] Document commands, exit codes, override behavior and remaining runtime gaps — specification and load-guide link inspected; 2026-10-17 08:27 ET.
- [ ] Run affected tests under five minutes and review Standards, Spec and GoF.
- [ ] Commit on the dedicated branch after the overlap guard passes.
- [ ] Learning → skill: name any required skill follow-up, or none.

## GoF consult

Read `rules/cli.py`, `bookkeeping/clean/config.py`, their history and the
gof-refactor-reviewer smell/refactoring/consequence references. Existing command
registration and target validation have established boundaries; keep them.
Use Python's topological sorting and the existing strict Rules loader rather
than introducing workflow, strategy or command class hierarchies. The extra
module owns only sequence configuration and reporting; runtime dependencies,
leases, authorization, pins and verification stay with their current owners.

## Verification boundary

Tests exercise the public `rules sequence check` command registered by
`rules.cli.register`, with invented source documents on disk. Test answers are
literal expected orders/statuses and known invalid configurations. No database,
provider or shared-store load is required for this offline boundary. Runtime
qualification remains governed by the source-readiness specifications.

## Evidence

- First test failed because the `sequence` command did not exist; after the
  implementation it passed. Expanded to deferred and transitive dependants,
  malformed graphs, unsupported/provider profiles, every committed source and
  target failures.
- Affected testmon run: **96 passed in 3.46 seconds**, covering the new command,
  Rules skill commands, Bookkeeping contracts and architecture boundaries.
- `git diff --check` and overlap guard passed (seven files).
- Operator clarification: "it is easy decoupling nothing else". Sources are
  independent; preferred order never creates a required dependency. The
  implementation does not enable old-input fallback or alter running work.
