# Eliminate redundant full gold builds inside bootstrap-next windows

Type: task
Status: claimed
Blocked by: none

## Question

How must `load_history` make every windowed `bootstrap-next` task silver-only
while preserving standalone `bootstrap-next` compatibility and exactly one
final full-universe `gold-refresh` after all Silver, fundamentals, ADV, and MDM
work completes?

## Required work

- Add an explicit runtime policy that suppresses gold build, Snowflake table
  export, and Snowflake run-manifest publication for a windowed
  `bootstrap-next` invocation without changing its Bronze/Silver work,
  discovery bookkeeping, or canonical Silver publication.
- Pass that policy only from `load_history`'s `WindowedBootstrap` Map. A
  standalone `bootstrap-next` invocation must retain its current gold behavior
  unless its caller explicitly selects Silver-only operation.
- Preserve `load_history`'s existing single `GoldRefresh` state after the MDM
  chain and keep it on the large task profile.
- Remove the obsolete medium-task memory warning that treats per-window
  `bootstrap-next` as a full-universe gold builder.
- Add command and generated-workflow regression tests proving window tasks
  cannot publish gold and the final gold refresh remains unique and ordered.

## Acceptance

- Focused tests prove Silver-only `bootstrap-next` never enters the gold build
  or writes a Snowflake export run manifest, while default standalone behavior
  remains compatible.
- The generated `load_history` definition passes the Silver-only policy to
  every window and contains exactly one `gold-refresh`, after MDM verification.
- An immutable-image production execution records zero per-window
  `gold_build_started` events and one final successful `gold-refresh`, with
  elapsed time and compute reduction compared with the prior run.

## Progress

Claimed by Codex on 2026-08-01. GoF/history review found no justified catalog
pattern: this is one explicit orchestration policy, and introducing Strategy or
Template Method would add indirection without a repeated variation axis. The
implementation will preserve the existing command path and make the execution
policy explicit at its composition boundary.

Implemented locally on `codex/bootstrap-next-silver-only`:

- Added explicit `bootstrap-next --silver-only` policy while keeping the
  standalone default gold/Snowflake behavior unchanged.
- Applied the flag only to `load_history`'s `WindowedBootstrap` Map and retained
  one large-profile `GoldRefresh` after `MdmVerify`.
- Centralized planned-write filtering so Silver-only executions omit gold
  manifests consistently in validation, pipeline tracking, and final writes.
- Preserved `seed-universe`'s separate Snowflake ticker-reference publication
  bookkeeping after code review identified it as a neighboring contract.
- Added actual bronze-capture tests proving Silver-only skips gold/export calls
  and standalone `bootstrap-next` still publishes, plus generated-state-machine
  and CLI regressions.

Local evidence on 2026-08-01: focused suites pass (74 tests); related pipeline,
seed, and submission suites pass (39 tests and 2 subtests); shell syntax,
changed-file lint, and diff checks pass. The full unit/architecture suite has
912 passing and 4 skipped tests, with only two parent-branch failures for the
unrelated `reduce-identity-refresh` command's missing scope/path catalog cases.
Production immutable-image execution evidence remains outstanding, so this
ticket stays claimed rather than resolved.
