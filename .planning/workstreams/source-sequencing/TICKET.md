# Source sequencing configuration check

Status: implemented and locally verified. Scope: offline configuration checking, not source activation
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
- [x] Run affected tests under five minutes and review Standards, Spec and GoF — 96 passed in 3.46s; diagnostic fix then 29 passed / 68 unchanged deselected in 0.60s; three independent reviews completed, Standards P2 fixed and rechecked; 2026-10-17 08:29 ET.
- [x] Commit on the dedicated branch after the overlap guard passes — `84a26332`, correct branch and no overlap verified; 2026-10-17 08:29 ET.
- [x] Fix CI packaging failure: include the sequencing module in the data wheel, verify a fresh installation and rerun affected tests — actual wheel omission reproduced, installed-bundle suite 80 passed in 283.36s, three review axes passed; 2026-10-17 08:43 ET.
- [ ] Recheck the updated PR's complete CI result.
- [x] Learning → skill: none — existing data-platform Source readiness rules already require independent progress, valid required inputs and separate qualification evidence. New command syntax and its offline limit belong in `docs/specs/source-sequencing.md`; no skill defect found; 2026-10-17 08:29 ET.

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
- Independent reviews: Spec and GoF found no blocking issue. Standards found
  raw malformed-sequence YAML diagnostics could echo private values. Added a
  failing public-command regression, replaced loader messages with a category,
  reran affected tests, and obtained the reviewer's explicit resolved finding.
- Real `edgar_warehouse.cli.main` calls verified all-source, Person-only and
  deferred-GLEIF reports. Documentation links resolve. Runtime readiness
  remains explicitly unchecked; no source load was performed.

## CI packaging follow-up

CI run `39032746991` had 19 installed-bundle failures with
`ModuleNotFoundError: edgar_warehouse.rules.sequence`; its other 1,018 engine
tests passed. The data wheel deliberately lists individual source-facing Rules
modules because Bookkeeping owns the shared Rules files in a separate wheel.
The new module was absent from that list. A real wheel build reproduced the
omission; adding its canonical file to the data wheel fixes ownership without
duplicating files across wheels.

GoF consult: inspected packaging history and wheel ownership before editing;
retain the explicit split, with no new abstraction. Standards, Spec and GoF
reviewed the package entry and installed-CLI regression with no findings.

Verification: wheel contains the Python module and bundled sequence YAML;
the complete affected installed-bundle suite passed 80 tests in 283.36 seconds.
Tests installed committed code, ran in Python isolated mode outside the checkout
and used disposable PostgreSQL stores. Test containers stopped on completion;
the existing shared and unrelated test containers were preserved. No provider
request or shared-store write. The existing installed-bundle qualification
requirements remain the skill guidance; no new skill defect was identified.
