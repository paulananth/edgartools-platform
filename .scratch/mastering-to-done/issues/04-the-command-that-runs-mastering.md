# The command that runs mastering

Type: grilling (HITL)
Status: resolved
Blocked by: none

## Question

The adopted mode names (platform validation, 2026-09-30) are:
- **Bookkeeping:** init, migrate, plan, validate, run, status, recover;
- **Change Journal:** init, migrate, plan, validate, deploy, status, recover-delivery.

The enabled CLI has none of plan, validate, deploy or recover-delivery. Today mastering is submitted through `rules run`, and `bookkeeping` has no `run` (review finding 3).

The decision has two parts:
- whether the operator runs mastering with `bookkeeping run --target mdm`, or keeps `rules run`;
- which of the missing modes get built and which get dropped from the skills.

## Answer

Operator, 2026-10-02 by 10:57 ET: "Keep `rules run` (Recommended)".

- **`edgar-warehouse rules run --target mdm` is the one command that runs mastering.** It submits the approved versions to the Bookkeeping runner. No `bookkeeping run` command is built.
- **The mode names are steps an agent follows** with existing commands, not commands of their own:
  - Bookkeeping's plan, validate and recover;
  - the Change Journal's plan, validate, deploy (`run_mode.py deploy`) and recover-delivery.
- **The Bookkeeping skill** now says so, in place of "not built yet".
- **Ticket 06 proves the command end to end** on the switch-on run. That closes review finding 3.

## Checklist

- [x] Operator decision recorded. 2026-10-02 by 10:57 ET
- [x] `skills/bookkeeping/SKILL.md` names the command and drops "not built yet". 2026-10-02 by 10:57 ET
- [ ] ~~Prove `rules run --target mdm` end to end~~ deferred to ticket 06: it runs on the switch-on database
- [x] PR, CI green, merge on the operator's word: #788, rebased on #785, merged 2026-10-02 12:36 ET (operator, 2026-10-02: "yes merge one by one and continue implementing ticket 14")
