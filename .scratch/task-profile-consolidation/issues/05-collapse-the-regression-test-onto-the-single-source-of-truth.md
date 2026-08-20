# 05 — Collapse the regression test onto the single source of truth

**What to build:** `tests/architecture/test_gold_affecting_commands_task_sizing.py`
currently has to reverse-engineer three independent mechanisms (its own
docstring documents this as the reason it exists — `GOLD_AFFECTING_COMMANDS`
membership could previously resolve task memory through
`workflow_profile()`'s case statement, `write_warehouse_mdm_gold_definition`'s
hardcoded params, or `bootstrap-next`'s special case, with no link between
them). With ticket 04 done, rewrite the test to assert against the single
ticket 01 mapping directly — every `GOLD_AFFECTING_COMMANDS` member resolves
to at least the required profile via the one shared lookup, full stop.

**Blocked by:** 04

**Status:** resolved (2026-08-19)

- [x] `test_gold_affecting_commands_task_sizing.py` asserts against the
      shared ticket 01 mapping, not three separately reverse-engineered
      mechanisms
- [x] The test's own docstring/comments no longer describe a three-path
      problem — they describe the single dispatch point
- [x] Full test suite green

## Answer

**Note on the file name:** the ticket refers to
`test_gold_affecting_commands_task_sizing.py` — that name is stale; the file
was already renamed to `tests/architecture/test_source_export_commands_task_sizing.py`
before this ticket (single-path-per-layer effort, unrelated rename off the
old "gold" naming that no longer matches the current layer map). Worked the
real, current file.

**Built:** removed all three-mechanism reverse-engineering machinery —
`_WAREHOUSE_MDM_GOLD_MEMBERS`, `_SPECIAL_CASED_PROFILE`,
`_resolve_workflow_profile`, `_run_warehouse_task_profile`, the
`_WORKFLOW_PROFILE_START`/`_WMG_START`/`_FAKE_*_ARN` markers and constants,
and the `write_warehouse_mdm_gold_definition`-generating machinery (temp
files, driver script, JSON parsing) that came with it. Replaced with one
helper, `_resolve_command_task_profile()`, that extracts and invokes the
real `command_task_profile()` bash function directly with each
`SOURCE_EXPORT_COMMANDS` member's real hyphenated name (no underscore
translation needed — `SOURCE_EXPORT_COMMANDS` members are already spelled
the same way `command_task_profile()` expects). `_gold_affecting_command_memory_mb()`
collapsed from a 3-branch dispatch to a single loop calling this one helper
for every member.

**Docstring/comments rewritten**, not just the code: the module docstring no
longer enumerates three independently-maintained mechanisms with per-path
resolution strategies — it states the single dispatch point directly and
notes tickets 01-04 as the history for readers who want it, without asking
the reader to hold three paths in their head to understand what the test
does today.

**Also decided while here:** `GOLD_BUILD_MEMORY_FLOOR_MB` bumped `4096 →
8192`. Ticket 01's own docstring had explicitly flagged this as stale
("today's actual minimum is technically 8192MB ... left to whoever next
revisits this file or ticket 05's collapse") without fixing it, deliberately
deferring the decision to this ticket. All 7 `SOURCE_EXPORT_COMMANDS`
members resolve to `"large"` (8192MB) today, so this is a pure tightening
(the `>=` assertion already held either way) that makes the floor match this
file's own stated invariant ("today's actual minimum ... not an
aspirational value") rather than leaving it silently 4096MB below reality.
Verified red-capable: temporarily set the floor to 16384MB, confirmed all 7
parametrized cases fail with a clear message, restored.

**`test_task_profile_source_of_truth.py`** got a short appended UPDATE note
(not a rewrite) recording that its sibling's three-mechanism reverse-
engineering is retired, and that the two files aren't yet fully redundant
(this one still covers 3 non-gold-affecting commands the sibling's scope
excludes, and still regenerates real ASL for two of its three paths rather
than calling `command_task_profile()` a second time) — so they're
deliberately left as two files, that decision left unmade here.

**Full suite:** `tests/architecture/` clean — 512 passed, plus the 2
pre-existing, already-documented, unrelated
`test_bootstrap_dbt_snowflake_secret.py` failures. mypy clean on both
touched files — and, as a side effect of removing the two-branch dispatch,
the one pre-existing type error in this file (`str | None` vs `str`
assignment, flagged as pre-existing-not-mine in tickets 02/03/04's work) is
now gone too, since the code shape that caused it no longer exists.
