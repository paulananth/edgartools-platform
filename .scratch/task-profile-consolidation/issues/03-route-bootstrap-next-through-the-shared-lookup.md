# 03 — Route bootstrap-next's special-cased profile through the shared lookup

**What to build:** `bootstrap-next` currently hardcodes its own task profile
(`"medium"`) as a special case, independent of both `workflow_profile()` and
`write_warehouse_mdm_gold_definition`. Switch it to consult ticket 01's
shared mapping instead, so all three original mechanisms collapse onto one
source of truth. This is a different call site from ticket 02 and can be
done in parallel with it.

**Blocked by:** 01

**Status:** resolved (2026-08-19)

- [x] `bootstrap-next`'s task profile resolution reads from the shared
      mapping instead of its own hardcoded `"medium"` special case
- [x] `bootstrap-next`'s resolved profile is unchanged from today's behavior
      (this ticket is a pure migration, not a profile change)

## Answer

**Note on the ticket title's "medium":** by the time this ticket was
implemented, ticket 01's mapping (and the real live wiring) had already
been corrected to `large`, not `medium` — see ticket 01's Answer
correction note, found and fixed while implementing this ticket. This
ticket routes `bootstrap-next` through the shared lookup at whatever value
that lookup holds (`large`); it was never about picking a specific value.

**Built:** `write_load_history_definition`
(`infra/scripts/deploy-aws-application.sh`) now resolves bootstrap-next's
per-window task profile via `command_task_profile bootstrap-next` (bash,
called internally, right after the function's parameter declarations) plus
a small `case` mapping the returned profile name to this function's own
existing `wh_task_small_arn`/`wh_task_medium_arn`/`wh_task_large_arn`
parameters — no new public parameter was added, and no dependency on
`task_definition_for_profile()`/the `TASK_DEF_*_ARN` globals was
introduced (those aren't otherwise needed by this function, and adding
them would have coupled it to state it's never depended on). The resolved
ARN (`bootstrap_next_task_arn`) is threaded into the existing python3
heredoc as one additional argv value, and `per_window`'s `ecs_state(...)`
call now uses it instead of the direct `wh_large_arn` reference.

**Proof this is a genuine routing change, not a coincidental value
match:** a new dedicated test file,
`tests/architecture/test_bootstrap_next_task_profile_routing.py`, sources
`command_task_profile()`'s real definition *and then redefines it with a
stub* immediately before invoking `write_load_history_definition` —
bash resolves function calls at call time, so a later definition
genuinely intercepts what the function calls at runtime. One test stubs
`command_task_profile` to answer `"small"` for `bootstrap-next` and
asserts `RunWindow`'s `TaskDefinition` flips to the small ARN (proving the
call is real, not vestigial); another stubs it to `fail` on any command
name other than the literal string `"bootstrap-next"` and asserts
generation still succeeds (proving the call passes the exact real CLI
command name, not some other spelling). A third confirms the unstubbed,
real value still resolves to `large`, matching ticket 01's mapping.

**Byte-identical ASL, verified analytically, not just asserted:** generated
`write_load_history_definition`'s full JSON from the commit immediately
before this change and from the current working tree (both with identical
fake ARNs), and diffed the two — `json.dumps(..., sort_keys=True)` output
was byte-for-byte identical. Zero behavioral change to the deployed state
machine; only the *source* of the ARN decision moved.

**Existing tests updated to source the new internal dependency:**
`write_load_history_definition`'s function body now calls
`command_task_profile()`, so every test that extracts and sources
`write_load_history_definition`'s source in isolation (bash function
resolution requires the callee to be defined in the same subprocess) needed
to also extract+source `command_task_profile()` first:
`tests/architecture/test_load_history_state_machine.py`'s `definition`
fixture, and `tests/architecture/test_task_profile_source_of_truth.py`'s
`_run_load_history_bootstrap_next_profile` helper. Both updated; all their
tests still pass.

**Full suite:** `tests/architecture/` green — 492 passed, plus the 2
pre-existing, already-documented, unrelated
`test_bootstrap_dbt_snowflake_secret.py` failures.
