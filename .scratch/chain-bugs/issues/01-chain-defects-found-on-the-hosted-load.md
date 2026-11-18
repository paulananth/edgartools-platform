# Chain defects found on the hosted load

Status: open
Type: task

Operator, 2026-11-18: "Are there any more bugs in loaders". Audited from the live load's own logs and the code.

## What the load's logs show

190 error blocks in the stores folder's `load-errors.log`: 128 are OpenFIGI's missing tickers file, 59 are silver's missing
temporary-table right (both fixed earlier, ticket 238), 3 are a run of 2026-11-15 (the file is never rotated and mixes runs).
No new cause appeared in today's run.

## Parts

- [x] The state file belonged to no store: a `done` line from a store dropped three days earlier was counted done today (shown:
  `done_steps` returned `company` from a 2026-11-15 line). It now names its store by the instance's address and a different
  store's file is set aside (2026-11-18 09:21 ET; `test_a_state_file_from_another_store_is_set_aside_so_its_done_lines_never_satisfy_a_wait`,
  `test_a_store_is_named_by_its_address_without_ever_showing_it`: `ensure_store`, `store_id` did not exist)
- [x] A failure that comes back unchanged was retried (OpenFIGI 8 attempts on one missing file, `13f-filings` 3): it stops at
  once, but a window that ran out still resumes (2026-11-18 09:21 ET; `test_a_retry_is_pointless_when_the_same_error_comes_back_but_not_when_the_window_ran_out`:
  `retry_is_pointless` did not exist)
- [x] The shared error log did not say which block was a step's: each attempt's errors are kept with the step, addresses
  hidden (2026-11-18 09:21 ET; `test_the_errors_an_attempt_wrote_to_the_shared_error_log_are_kept_with_that_step`: `errors_since` did not exist)
- [x] `ipo` had a 60-minute window for 149 bundles at about two minutes each, one at a time, and ended attempt 1 with bundles
  unfinished: 120 minutes, 4 attempts (2026-11-18 09:21 ET; `test_ipo_has_a_window_that_fits_its_bundles`: 60 x 3 = 180 < 300)
- [ ] `load --plan` reports a step "blocked None" while a file its rules read beside the capture is missing (OpenFIGI: 128
  failures over 8 attempts): it must name a missing file and a missing right before the first load. This is in the load
  code, a pinned runtime file, so it waits for the hosted load to end
- [ ] `load-errors.log` is never rotated and mixes runs; the load names "its message" without saying which block (the load
  code)
- [ ] The scheduler (`--auto`) has run only against fakes: run it once on a disposable store before trusting it on a real one
- [x] A review found address redaction missed `postgresql+psycopg2://` in the attempt note and hid no value named like a secret:
  one `redact` hides every address form and the value of any key named `password`, `secret`, `token`, `key`, `dsn` or `url`
  (2026-11-18 09:23 ET; `test_redaction_hides_every_address_form_and_every_value_named_like_a_secret`: `redact` did not exist, and the old
  pattern left `postgresql+psycopg2://u:pw@h` unchanged)
- [x] Spec review, six findings fixed (2026-11-18 09:25 ET; 71 tests, each failing first):
  - a state file with lines and no marker may be another store's, so neither setting it aside (it breaks a run in progress that
    appends to it) nor adopting it silently (it reintroduces the stale lines) is right: the run stops and asks, `--adopt-state`
    is the operator's word (`test_a_state_file_with_lines_and_no_marker_asks_the_operator_and_is_adopted_only_on_their_word`);
  - two lanes starting at once lost the archive in 156 of 200 trials and crashed in 44: a lock and a re-read under it
    (`test_two_lanes_starting_at_once_against_another_stores_file_set_it_aside_once_and_lose_nothing`);
  - `store_id` crashed on an unescaped `/` in a password, and an empty URL or two sockets gave distinct stores one name: the
    default port and the host's case are normalised, a socket names its directory, and no host is an error
    (`test_a_store_is_named_by_its_address_without_ever_showing_it`,
    `test_a_url_that_names_no_host_is_an_error_not_a_shared_name_and_a_socket_names_its_directory`);
  - `retry_is_pointless` stopped a step whose bundle moved from 17 to 230, and a lock or deadlock that clears: it now needs the
    identical error, nothing moved, and not a lock, deadlock, lost connection or window
    (`test_a_retry_is_pointless_only_when_the_same_error_comes_back_with_nothing_moved_and_not_a_lock_or_the_window`);
  - a step's errors file held another lane's block written in the same window: it keeps only the blocks of the step's own
    source and target (`test_the_errors_an_attempt_wrote_to_the_shared_error_log_are_kept_with_that_step_and_not_another_lanes`);
  - the store check ran before `--workers` was validated, so a refused command had already set the file aside: it runs after
- [x] Redaction: one `redact` hides every address form and the value of any key named `password`, `secret`, `token`, `key`,
  `dsn` or `url` (2026-11-18 09:25 ET; `test_redaction_hides_every_address_form_and_every_value_named_like_a_secret`: `redact` did not
  exist, and the old pattern left `postgresql+psycopg2://u:pw@h` unchanged)
- [x] Learning → skill: the data-operations skill and the initialize and daily-run runbooks say the state file names its
  store, a step's errors are kept with it, and an unchanged failure stops (2026-11-18 09:23 ET; the skill lints pass: bundle
  portability, role skills, no tickets in skills)
