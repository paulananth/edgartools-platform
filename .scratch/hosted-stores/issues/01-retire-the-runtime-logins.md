# Retire the six runtime logins with a committed command

Status: open
Type: task

Operator, 2026-11-18: "Why can't we do this now ... retire the old runtime logins" (ticket 238 had it as a manual `ALTER ROLE` after the
chain).

## Findings

- Every load connects as `edgar_loader`, a member of the six runtime roles, so those roles no longer need to be logins.
- No committed command made them NOLOGIN: the ticket said to run `ALTER ROLE` by hand, which the repo's rule (committed commands only)
  does not allow.

## Parts

- [x] `provision_hosted_store.py --retire` makes each of `mdm_runtime`, `rdm_runtime`, `rules_agent`, `bookkeeping_runtime`,
  `change_journal_runtime` and `silver_runtime` a NOLOGIN group, checks all six before changing any, never touches the loader, and
  refuses while any session holds one (2026-11-18 15:40 ET; `test_the_six_runtime_logins_become_groups_and_the_loader_is_never_touched`:
  `ImportError: cannot import name 'retire'`; `test_a_runtime_login_a_session_still_holds_refuses_before_any_is_retired`;
  `test_a_role_that_cannot_log_in_or_is_absent_is_left_alone`)
- [x] The initialize runbook and the data-operations skill say so (2026-11-18 15:40 ET; both read in the PR)
- [ ] Run it on the hosted instance once the loads that started under the old logins have ended, then `doctor` and one small load
  under `edgar_loader`
- [x] Learning → skill: data-operations "One login for every load" and the init runbook's step 2 (2026-11-18 15:40 ET; both read in the PR)
