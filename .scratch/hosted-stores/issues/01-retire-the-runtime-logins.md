# Retire the six runtime logins with a committed command

Status: resolved
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
- [x] Run on the hosted instance with the load stopped: 11 runtime URLs moved to the loader across the stores folder, six roles retired,
  the loader still creates nothing in any of the six databases, `doctor` ok, and a fresh load running under it (2026-11-18 15:54 ET; live)
- [x] A review of this change found the live problem first: retiring without moving the URLs in `connection.env` and `governance.env` made
  provisioning refuse ("bookkeeping_runtime exists and cannot log in"). `--loader` now moves every stores file, `--retire` refuses while a URL
  names a runtime role, retirement runs last, and the sessions are counted after the change and the change undone if any remain (2026-11-18 15:54 ET;
  `test_every_runtime_url_in_every_stores_file_becomes_the_loader_login_and_the_old_files_are_kept`, `test_a_url_that_still_names_a_runtime_role_refuses_before_anything_changes`,
  `test_a_session_logged_in_as_a_runtime_role_refuses_the_run_and_leaves_every_role_a_login`, `test_provisioning_runs_again_after_the_retirement_once_no_url_names_a_runtime_login`)
- [x] Learning → skill: data-operations "One login for every load" and the init runbook's step 2 (2026-11-18 15:40 ET; both read in the PR)
