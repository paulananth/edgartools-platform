# What exactly is the measured-load procedure, run by run?

Type: task
Status: open
Blocked by: 01, 07

## Question

The plan's measurement procedure is specified only in outline. This ticket settles the mechanics
that a runner must follow, so two runs of it produce comparable numbers.

Decide and record, for one approved target:

1. The exact command, with every flag spelled out: source, target, capture folder, capture run ID,
   stores folder, `--workers 1 --bundles 1 --minutes 120`, the declared `--fact name=value` and
   `--file name=path` inputs, `--plan` first and the same command without `--plan` after approval.
2. Where the per-target private log is written, its mode, and the rule that it is never printed to
   the chat.
3. How the invocation is bracketed: ET timestamps before and after, `time -p`, and the two derived
   figures — `active_command_seconds` as the sum of `time`'s `real` across invocations, and
   `target_wall_seconds` as final verified completion minus the first invocation start, including
   pauses and resumes.
4. The exact `profile_load.py steps` invocation per bundle run ID, and how its event intervals map
   onto the report's step-interval fields, including the `mdm.prepare` + `mastering.merge` sum that
   becomes `mdm_write_step_seconds`.
5. What to do when `load` reports `selected = 0`: no run, no timing, and the historical evidence
   carried forward instead.
6. The order of targets, and how the three declared link targets (`gleif/subfund-pairs`,
   `iapd.adv/custodians`, `sec.ownership/security_symbols`) are sequenced against their consumers.

This ticket may be AFK where the mechanics follow from the repository's existing commands and
skills, and HITL only where a choice remains. Record the resolved procedure in the ticket, and
append a one-line gist to the map's Decisions so far.
