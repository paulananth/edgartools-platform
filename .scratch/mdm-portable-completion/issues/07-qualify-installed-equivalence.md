# Qualify the installed MDM workflow on both engines

Type: task
Status: resolved
Assignee: Codex
Claimed: 2026-10-25 22:43 ET; resumed by Codex on a fresh main worktree
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: none; reader #1164/#1165 and worker #1171/#1173 implementations and guidance merged

## Question

Does the independently installed normal workflow prove equivalent complete behavior on PostgreSQL and MySQL?

## Parts

- [x] Pin the independent installed-caller case matrix, actual public call surfaces and revision/evidence contract before execution. — 2026-10-23 20:38 ET; 18 distinct families and existing source entry points checked against the caller inventory and current definitions.

- [x] Install the committed bundle outside the checkout and run the normal migration, configured worker, Merge Stage, context, master lookup and publication paths on each real engine. — 2026-10-26 06:52 ET; five-wheel isolated installation and normal callers; 160 installed cases pass per engine in CI.
- [x] Cover invented vocabulary, identity uniqueness, held-back records, relationships, history/details, concurrency, stale work, interruption, recovery, populated upgrades and unchanged replay. — 2026-10-26 06:52 ET; all 18 families pass on both configured kinds and both engines.
- [x] Record counts and outcomes tied to the tested revision; run affected tests only, below the local five-minute cap per run; retain SQL Server adapter checks without claiming full qualification. — 2026-10-26 06:52 ET; 320 retained case outcomes; matching per-case configuration hashes and verified cleanup; retained SQL Server adapter CI passes.
- [x] Review Standards, Spec and GoF and resolve material findings; ensure the tested code is the installed code. — 2026-10-26 06:52 ET; implementation review below; four affected architecture checks and complete CI pass.
- [x] Expand installed cases for populated upgrade, every durable-effect rollback boundary, exact values and field/profile/kind transitions; retain explicit failures for unsupported behavior. — 2026-10-26 06:52 ET; 36 boundary cases pass per engine, including nine durable groups with detail-history rollback.
- [x] Freeze per-case results and all 18 family outcomes on both engines; qualify final CI and update the diagram without implying source activation. — 2026-10-26 06:52 ET; all 36 family slots qualified; 21 CI checks green; updated simple Lavish diagram inspected.
- [x] Learning → skill: update its owning skill on a separate branch/PR, or record none. — 2026-10-26 06:52 ET; mdm-engineering Independent installed qualification and Worker authority and input publication; separate PR #1179, 8 affected local checks pass; the prior skill head passed all 13 CI checks and alias-guidance closeout CI remains required before merge.

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

## Preparation record (historical)

[Installed workflow qualification matrix](../assets/installed-workflow-qualification.md)
pins the required normal callers and outcomes. The first part is reviewed
against the caller inventory and current definitions; the execution parts
remain unchecked.

## Preparation review

Resumed from merged main 36e6008d in `codex/mdm-full-workflow-proof-20261025`,
preserving the earlier matrix commit. The available GoF reviewer and the
histories of the installed worker and bundle fixtures support retaining the
existing facade and normal scenarios. The new harness copies test scaffolding
outside the checkout and uses isolated Python; every runtime/native import and
all five wheel revisions must resolve to the independently installed bundle.
No alternate merge or owner-seeded identity path is introduced. Installed
qualification gets its own bounded PostgreSQL/MySQL CI jobs, preserving the
existing storage suites and their budgets.

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

## Development checkpoint (historical)

Rebased without conflicts onto main through the identifier-list changes in
#1175–#1177. Five committed packages at 658492dc were independently rebuilt;
package file-manifest hashes are retained privately. Both configured kinds
pass 36 targeted boundary cases per engine: 18 upgrade, exact-value, profile,
identifier-order and authority checks, and 18 durable-group rollback checks.
These development-harness results are historical until final-revision CI passes.
PR #1178 owns the complete 160-case matrix per engine. Eight required CI jobs
retain only per-case counts/outcomes, with private raw diagnostics excluded.
Skill lessons are separately reviewed in PR #1179; eight affected genericity
checks pass locally.

### Standards — implementation review

Fresh dedicated branch and overlap guards; tests and CI only, no runtime,
migration, source or hosted-store changes. Local invocations remain bounded
below five minutes. Four affected architecture checks pass. Public artifacts
contain counts and invented test vocabulary. Final CI and complete slot
accounting remain required.

### Spec — implementation review

The manifest enumerates all 18 families and two configured kinds, including
normal worker arrival order and separate worker/verifier processes. Both
engines use the same installed runtime and fixture scenarios. Refusal tests
accept a valid control first and assert the intended destination error. Every
case checks the five installed package revisions and runtime import paths.
Full qualification remains open until every final-revision case passes.

### GoF — implementation review

Available gof-refactor-reviewer applied to the fixture, caller history and
resulting diff. Retain existing Store/facade/Adapter interfaces and scenario
functions. The case dispatch is test enumeration; no repeated production
variation justifies a new class hierarchy or alternate writer.

## Final qualification

[Complete CI and retained outcomes](https://github.com/paulananth/edgartools-platform/actions/runs/40307681836) pass on PR head `d11505350226f03050429725d006e79b457d6e4d`;
all five installed packages use tested revision `cc8b30407e5ab397151e7518f33c9359e9abb068`.
Both engines pass 160 cases, both configured kinds and all 18 families.
Every retained case confirms cleanup; configuration hashes match across engines.
The three empty collection placeholders outside the workers group qualify no
slot; both real separate-worker cases run and pass in that group.

Qualification is complete. PR #1178 and separate skill PR #1179 still require
named merge approval. Source activation, hosted migrations, SQL retirement,
Silver follow-up and full SQL Server workflow qualification are separate gates.

The qualification upload contained 356 identical temporary-directory alias
copies alongside the 320 canonical outcomes. Canonical paths and identical
bytes were verified before counting; the closeout excludes these aliases from
future uploads. The affected architecture checks pass; final closeout CI is
required before merge.
