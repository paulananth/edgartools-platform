# Qualify the installed MDM workflow on both engines

Type: task
Status: claimed
Assignee: Codex
Claimed: 2026-10-23 20:37 ET
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 05, 06

## Question

Does the independently installed normal workflow prove equivalent complete behavior on PostgreSQL and MySQL?

## Parts

- [x] Pin the independent installed-caller case matrix, actual public call surfaces and revision/evidence contract before execution. — 2026-10-23 20:38 ET; 18 distinct families and existing source entry points checked against the caller inventory and current definitions.

- [ ] Install the committed bundle outside the checkout and run the normal migration, configured worker, Merge Stage, context, master lookup and publication paths on each real engine.
- [ ] Cover invented vocabulary, identity uniqueness, held-back records, relationships, history/details, concurrency, stale work, interruption, recovery, populated upgrades and unchanged replay.
- [ ] Record counts and outcomes tied to the tested revision; run affected tests only, below the local five-minute cap per run; retain SQL Server adapter checks without claiming full qualification.
- [ ] Review Standards, Spec and GoF and resolve material findings; ensure the tested code is the installed code.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

## Acceptance evidence

Both independently installed normal callers pass the full case matrix. Adapter-only checks and PostgreSQL-only proofs cannot close this gate.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.

## Operator priority

Lavish feedback on 2026-10-23: “start this” on the installed two-engine workflow
proof. Start the independent qualification specification and harness preparation
now. Retain prerequisites 05/06 (and their atomic-save prerequisite 04) for full
execution. PR #1156 implements only the read phase; its installed smoke checks
cannot close this ticket. No owner-seeded or helper-only result will be counted
as normal workflow proof.

## Work in progress

[Installed workflow qualification matrix](../assets/installed-workflow-qualification.md)
pins the required normal callers and outcomes. The first part is reviewed
against the caller inventory and current definitions; the execution parts
remain unchecked.

## Preparation review

### Standards

Fresh dedicated branch/worktree from current main; counts and intended outcomes
only. No test execution, source access, schema change, activation or merge is
claimed by this preparation. Each actual local run will retain the five-minute
cap and stop its own resources.

### Spec

The 18 families require normal installed callers on both engines and enumerate
competing writers, stale/no-identity proposals, rollback, recovery and replay.
Tests must expand each family per configured kind/source and fault boundary.
A helper or owner-seeded result cannot close normal workflow proof.

### GoF

The available gof-refactor-reviewer method applied to the caller inventory and
current Merge Stage/Store surfaces supports the existing Adapter/facade seam.
This specification introduces no alternate policy interpreter, store hierarchy
or test-only writer. Implementation/harness code receives its own consult and
three-axis review before execution.
