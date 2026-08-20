# 07 — Decide whether to revert load_history's SeedUniverse off large now that the root-cause hydrate fix is live

Type: grilling

**What to build:** Not a build — a decision. `load_history`'s own
`SeedUniverse` state (inside `write_load_history_definition`) has been
hardcoded to `wh_large_arn` since 2026-08-09, a same-day emergency bump
after a live exit-137 OOM (`seed-universe`'s dispatch unconditionally
buffering the entire canonical `silver.duckdb` into memory during hydrate,
before any per-command filtering logic ran).

That root cause is now fixed and confirmed live in prod (see ticket 06,
`.scratch/task-profile-consolidation/issues/
06-decide-seed-universe-profile-discrepancy.md`, resolved 2026-08-20):
streaming hydrate (PR #392) plus moving `seed-universe`'s novelty-detection
filter off silver onto MDM (PR #394). Ticket 06 kept
`command_task_profile()`'s standalone-workflow-facing `seed-universe` entry
at `medium` on the strength of that fix plus today's canonical size (1.5GiB,
comfortably inside medium's 4096MB envelope for the one remaining unpatched
risk — the merge/publish step's own full-buffer read/write, deliberately
deferred elsewhere, not proven unsafe).

The `seed-universe-narrow-hydrate` wayfinder map's own stated Destination
explicitly named this exact question — *"reaching the end of this map means
deciding, for seed-universe specifically, whether it can move back to a
smaller profile once both are in place"* — but that map closed its Frontier
("None... this map's destination is reached") without a
`## Decisions so far` entry ever actually answering it. This ticket exists
to close that gap for the `load_history`-specific half of the question
(ticket 06 already closed it for the standalone-workflow half).

**Discovered while:** implementing task-profile-consolidation ticket 06
(2026-08-20), investigating the standalone-vs-load_history `seed-universe`
profile discrepancy. Not independently investigated further at the time —
out of ticket 06's own stated scope (its acceptance criteria name only
`command_task_profile()`'s single entry, not load_history's separate
hardcoded parameter).

**Blocked by:** None — can start immediately

**Status:** resolved (2026-08-20)

## Question

Should `write_load_history_definition`'s `SeedUniverse` state be reverted
from `wh_large_arn` back to `wh_task_medium_arn` (converging with
`command_task_profile()`'s `seed-universe` entry, per ticket 06's decision),
or does `load_history`'s own invocation pattern carry a real, still-live
reason to stay on `large` that the standalone workflow doesn't share?

- [x] Determine whether `load_history`'s `SeedUniverse` state genuinely
      seeds against a larger/different universe than the standalone
      workflow, or any other load_history-specific factor (e.g. running
      concurrently with other Stage 0/1 work on the same task, different
      timing relative to canonical's growth) that could keep the merge/
      publish step's still-unpatched full-buffer risk closer to medium's
      4096MB ceiling than the standalone workflow's invocation
- [x] Either revert `write_load_history_definition`'s `SeedUniverse` state
      to `wh_task_medium_arn` (if no such difference exists, converging
      both call sites downward per ticket 06's same reasoning), or record
      the specific, load_history-only reason it should stay on `large`
- [x] If reverted, thread the change through the same genuine-routing proof
      technique tickets 02/03/04 of this same effort established (not just
      a value change with no test coverage) and re-verify byte-identical
      ASL for every other state `write_load_history_definition` builds
- [x] Once decided, update the `seed-universe-narrow-hydrate` map
      (`.scratch/seed-universe-narrow-hydrate/map.md`) with a
      `## Decisions so far` entry closing its own previously-unresolved
      stated destination, not just this ticket

## Answer

**No load_history-specific difference found.** `write_load_history_definition`'s
`SeedUniverse` state calls `States.Array('seed-universe', '--run-id',
$$.Execution.Name)` -- byte-identical to the standalone `seed_universe`
workflow's own command expression
(`workflow_command_expression`'s `seed_universe` case, same literal
`'seed-universe', '--run-id', $$.Execution.Name` args). Both read/write the
same shared canonical `silver.duckdb` (there is only one canonical file;
its size at any moment doesn't depend on which caller last touched it —
confirmed via the growth trail across this session's own tickets/research,
1.07GB (2026-07 era) -> 1.17GB -> 1.25GB -> 1.5GiB (2026-08-20), a shared
trend independent of caller). `load_history`'s `SeedUniverse` runs under
the `sec_fetch_active` lease as a single sequential step (`MaxConcurrency=1`
throughout Stage 1), so there's no concurrent same-task memory pressure
from sibling Stage 0/1 work either. Presented this evidence to the user via
AskUserQuestion; **user confirmed: revert to medium.**

**Implementation:** added a `seed_universe_profile`/`seed_universe_task_arn`
bash resolution block mirroring ticket 03's `bootstrap_next_profile`
pattern exactly -- `command_task_profile seed-universe` resolved in bash,
passed into the python heredoc as a new argv value, and the `SeedUniverse`
`ecs_state()` call switched from the hardcoded `wh_large_arn` to
`seed_universe_task_arn`. Same single source of truth
(`command_task_profile()`) now governs both call sites, so a future change
to `seed-universe`'s profile can't silently diverge between them again.

**Genuine-routing proof:** new
`tests/architecture/test_seed_universe_task_profile_routing.py`, mirroring
`test_bootstrap_next_task_profile_routing.py`'s technique exactly (3 tests:
real-value match, stub-override interception proof, exact-command-name
strict stub). Had to also patch the two existing
`test_bootstrap_next_task_profile_routing.py` stub-override tests and the
new file's own stub overrides to handle *both* `bootstrap-next` and
`seed-universe` calls -- `write_load_history_definition` now calls
`command_task_profile()` twice in one function body, so a stub that only
recognizes one command name and `fail()`s on any other unexpected call
would break on the sibling call.

**Byte-identical ASL re-verification:** generated `write_load_history_definition`'s
full JSON before (git `HEAD`) and after this change with identical fake
ARNs, deep-diffed every key. Single diff: `.States.SeedUniverse.Parameters.TaskDefinition`,
`arn:wh-large -> arn:wh-medium`. No other state changed shape or value. This
was first done as an ad-hoc, uncommitted script -- the Spec-axis code review
correctly flagged that as insufficient for an auditable checklist item (an
unreproducible claim, the same class of gap this repo's own 5-whys
conventions warn about). Fixed by committing the same guarantee as a real
test: `test_every_states_task_definition_matches_expected_profile` in
`test_load_history_state_machine.py` walks every state in the full
definition (including nested inside Map/Parallel) and asserts the complete,
exact state-name -> TaskDefinition-ARN mapping, not just SeedUniverse's own
value in isolation -- so any future change that accidentally shifts another
state's task profile fails reproducibly in CI, not just once by hand.

**Documentation:** updated `command_task_profile()`'s own `seed-universe`
comment (previously said this value "reflects the standalone seed_universe
workflow only") to note both call sites now converge on it; updated
`SeedUniverse`'s own comment block in `write_load_history_definition` to
record the revert and its reasoning; closed the
`seed-universe-narrow-hydrate` map's own previously-unrecorded destination
question with a `## Decisions so far` entry pointing back here. The
Standards-axis code review also caught two other docstrings in
`test_load_history_state_machine.py` (`test_stage1b_maps_use_large_task_definition`
and `test_windowed_bootstrap_uses_large_task_definition`) that this diff's
own file-touch left stale -- both cited SeedUniverse as still being on the
large-profile precedent, which this same change just reverted. Fixed both
to note the divergence explicitly rather than silently going stale.

Tests: 95 passed across the full task-profile-consolidation architecture
test set (`test_load_history_state_machine.py`,
`test_bootstrap_next_task_profile_routing.py`,
`test_seed_universe_task_profile_routing.py`,
`test_task_profile_source_of_truth.py`,
`test_workflow_profile_pass_through_routing.py`,
`test_source_export_commands_task_sizing.py`) -- 95, not 94, after adding
`test_every_states_task_definition_matches_expected_profile`. Full
`tests/architecture/` suite: 516 passed, 2 failed (the same pre-existing,
unrelated `test_bootstrap_dbt_snowflake_secret.py` failures noted
throughout this effort). Full repo suite: 2265 passed, 4 skipped, same 2
pre-existing failures (re-run after the code-review fixes above; unchanged
from the earlier run before those fixes).

**Code review:** ran `/code-review` (Standards + Spec sub-agents in
parallel) against this diff. Standards: no hard violations in the core
implementation; one real hard violation found and fixed (the two stale
docstrings above) plus two judgement calls noted but not acted on (narration
of one decision repeated across six files/comments -- defensible given this
repo's wayfinder-documentation convention; the `seed_universe_profile`/
`seed_universe_task_arn` bash block is a verbatim structural copy of the
pre-existing `bootstrap_next_profile` block -- intentional precedent-
following per the ticket's own stated intent, second occurrence, not yet
rule-of-three). Bash quoting in both test files' stub-override strings
explicitly checked clean (no stray `\$` escapes). Spec: one real gap found
and fixed (the byte-identical-ASL claim's ad-hoc-script gap, above); no
scope creep; no implemented-but-wrong findings.

**Not yet deployed as of this entry** -- code-only change, same as tickets
02-06; needs the next `deploy-aws-application.sh --env prod` run (no image
rebuild required, this is Step Functions ASL generation only) to take
effect live.
