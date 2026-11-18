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
- [x] Learning → skill: the data-operations skill and the initialize and daily-run runbooks say the state file names its
  store, a step's errors are kept with it, and an unchanged failure stops (2026-11-18 09:21 ET)
