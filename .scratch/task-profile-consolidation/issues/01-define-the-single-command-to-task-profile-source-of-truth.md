# 01 — Define the single command→task-profile source of truth

**What to build:** Today, an ECS command's task memory/CPU profile is resolved
through three independent mechanisms that can silently disagree:
`infra/scripts/deploy-aws-application.sh`'s `workflow_profile()` case
statement (lines ~1332–1358, with dead cases for `daily_incremental` and
`bootstrap` that nothing ever calls), `write_warehouse_mdm_gold_definition`'s
hardcoded `wh_task_large_arn`/`wh_task_medium_arn` parameters (lines
~3053–3850), and `bootstrap-next`'s own special-cased hardcoded `"medium"`.
Build one mapping from command name → task profile that is the single source
of truth going forward, added *alongside* the existing three mechanisms
without switching any caller over yet (expand step — nothing behavioral
changes in this ticket). This is the prefactor that makes tickets 02–04 safe,
mechanical migrations instead of judgment calls.

**Blocked by:** None — can start immediately

**Status:** resolved (2026-08-19)

- [x] A single mapping (command name → task profile) exists and covers every
      command currently resolved by any of the three existing mechanisms
- [x] A test asserts the new mapping matches each command's *current real*
      resolved profile today (i.e., it encodes today's live behavior,
      including the two dead `workflow_profile()` cases resolving to
      whatever `write_warehouse_mdm_gold_definition` actually hardcodes for
      them) — this is what makes tickets 02–04 provably behavior-preserving
- [x] Nothing that currently calls `workflow_profile()`,
      `write_warehouse_mdm_gold_definition`'s hardcoded params, or
      `bootstrap-next`'s special case is changed to use the new mapping yet

## Answer

**Built:** a new `command_task_profile()` bash function in
`infra/scripts/deploy-aws-application.sh`, added immediately after
`workflow_profile()` (same file, same style — a `case` statement returning
`small`/`medium`/`large`, not an associative array, matching this repo's
existing bash-3.2-on-macOS-portability convention). Keyed by the real
CLI command name (hyphenated, e.g. `daily-incremental`, `bootstrap-next`) —
not `workflow_profile()`'s underscore-workflow-name spelling — since that's
what tickets 02/03's real call sites will eventually pass, and the
underscore form only ever existed as an artifact of Step Functions workflow
names, not anything the CLI itself uses.

**Command set covered (10 commands — the union of what all three legacy
mechanisms answer for today, not just the `SOURCE_EXPORT_COMMANDS`
gold-affecting subset):**

| Command | Profile | Legacy mechanism today |
|---|---|---|
| `bootstrap-full` | large | `workflow_profile()` (live) |
| `targeted-resync` | large | `workflow_profile()` (live) |
| `full-reconcile` | large | `workflow_profile()` (live) |
| `load-daily-form-index-for-date` | small | `workflow_profile()` (live) |
| `catch-up-daily-form-index` | small | `workflow_profile()` (live) |
| `gold-refresh` | large | `workflow_profile()` (live) |
| `seed-universe` | medium | `workflow_profile()` (live) |
| `daily-incremental` | large | `write_warehouse_mdm_gold_definition`'s `RunWarehouseTask` (`workflow_profile()`'s case is dead code) |
| `bootstrap` | large | `write_warehouse_mdm_gold_definition`'s `RunWarehouseTask` (`workflow_profile()`'s case is dead code) |
| `bootstrap-next` | large | hardcoded directly in `write_load_history_definition` |

**Test:** `tests/architecture/test_task_profile_source_of_truth.py`, new
file (mirrors, and deliberately duplicates rather than imports from,
`test_source_export_commands_task_sizing.py`'s extraction/dispatch
technique — that file is explicitly collapsed onto this new mapping by
ticket 05, blocked on 04, so touching it now would be premature). For each
of the 10 commands: `test_command_task_profile_matches_current_live_behavior`
resolves the command's profile via `command_task_profile()` (the new
function, invoked as real bash, not re-implemented in Python) and
separately via whichever legacy mechanism actually governs it live today —
`workflow_profile()` invoked directly for the 7 commands it really answers
for, `write_warehouse_mdm_gold_definition`'s generated ASL inspected for
`RunWarehouseTask`'s actual `TaskDefinition` ARN for `bootstrap`/
`daily-incremental` (proving the new mapping's `large` matches *live*
behavior, not `workflow_profile()`'s unreached dead-code declaration — they
happen to already agree, but the test doesn't take that on faith), and the
documented `bootstrap-next` → medium hardcode for the last one — then
asserts the two answers are equal. `test_command_task_profile_covers_every_legacy_command`
confirms all 10 resolve without error, and
`test_command_task_profile_rejects_unknown_command` confirms an unmapped
name fails loudly (`fail`, exit 1) rather than silently defaulting — the
same "fail closed" contract `workflow_profile()` already has.

**Purely additive, confirmed:** `git diff --stat` shows only
`infra/scripts/deploy-aws-application.sh` (43 insertions, 0 deletions) plus
the new test file — no existing function, call site, or state-machine
generation logic was touched. `bash -n` confirms the script still parses.
Full `tests/architecture/` suite green (489 passed) apart from the 2
pre-existing, already-documented, unrelated
`test_bootstrap_dbt_snowflake_secret.py` failures.

Tickets 02 and 03 (both blocked by this one) can now proceed in parallel —
each has exactly one call site to migrate (`write_warehouse_mdm_gold_definition`'s
`RunWarehouseTask`/hardcoded warehouse ARNs, and `bootstrap-next`'s
`write_load_history_definition` hardcode, respectively) against this proven
mapping, with zero judgment calls about what the "right" profile is for any
command — that question is already answered and tested here.

**CORRECTION (2026-08-19, found while implementing ticket 03):** the
`bootstrap-next` row above originally said **medium**, not large — wrong,
and not a fresh mistake: it was copied uncritically from
`test_source_export_commands_task_sizing.py`'s own `_SPECIAL_CASED_PROFILE`
hardcode, which was itself stale since 2026-08-10 (the real
`write_load_history_definition` wiring was bumped to `wh_large_arn` after a
live exit-137 OOM on medium — see that day's comment above the `per_window
= ecs_state(wh_large_arn, ...)` call, and
`test_load_history_state_machine.py`'s
`test_windowed_bootstrap_uses_large_task_definition`, which had already
been asserting `large` for months). Ticket 01's own acceptance criterion 2
("a test asserts the new mapping matches each command's *current real*
resolved profile") was technically violated for exactly this one entry —
the original test's `_SPECIAL_CASED_PROFILE = {"bootstrap-next": "medium"}`
documented an assumption rather than deriving it from live-generated ASL,
unlike the other 9 entries. Had this gone uncorrected, ticket 03's "pure
migration" would have flipped the live wiring from large back to medium and
reintroduced the exact OOM the 2026-08-10 fix cured.

**Fixed:** `command_task_profile()`'s `bootstrap-next` case corrected to
`large`. `tests/architecture/test_task_profile_source_of_truth.py` upgraded
to derive bootstrap-next's expected value from real `write_load_history_definition`
ASL generation (reading `WindowedBootstrap`/`RunWindow`'s actual
`TaskDefinition`, same technique already used for `bootstrap`/
`daily-incremental`) instead of a hardcoded `_SPECIAL_CASED_PROFILE` entry —
closing the exact verification gap that let the drift go unnoticed.
Verified the new test is real (not vacuously passing) by temporarily
reverting the fix and confirming the test fails red, then restoring it.
`test_source_export_commands_task_sizing.py`'s identical stale assumption
was fixed too (`_SPECIAL_CASED_PROFILE["bootstrap-next"]`: medium → large),
so the two files stop disagreeing about the same command.

**Known, deliberately unresolved discrepancy surfaced by this correction:**
while re-deriving `write_load_history_definition`'s real wiring, found that
its own `SeedUniverse` state also runs the `seed-universe` CLI command — the
*same* command `command_task_profile()`'s `seed-universe → medium` entry
already covers via the standalone `workflow_profile()` mechanism — but on
`wh_large_arn`, not medium (also a 2026-08-09 OOM fix, same root cause
class). This means the claim "the three mechanisms already silently agree
on every command today" is **not actually true for `seed-universe`** — a
genuine, currently-live disagreement between two call sites for the
identical command, not a stale comment. Neither ticket 02 nor 03 touches
`SeedUniverse` or the standalone `seed_universe` workflow, so left
unresolved here rather than picking a side unilaterally (unverified whether
the standalone workflow is *also* at OOM risk on medium). Opened as ticket
06 (grilling — needs a human decision, not something an agent should
resolve solo).

Also flagged, not fixed: with this correction, all 7 `SOURCE_EXPORT_COMMANDS`
members now resolve to `large` — `test_source_export_commands_task_sizing.py`'s
`GOLD_BUILD_MEMORY_FLOOR_MB = 4096` no longer matches its own docstring's
claim of being "today's actual minimum" (that's now 8192MB). Not a
correctness bug (the assertion is `>=`, so it still passes) — a deliberate
tightening decision left unmade, noted in that file's docstring for whoever
next revisits it.
