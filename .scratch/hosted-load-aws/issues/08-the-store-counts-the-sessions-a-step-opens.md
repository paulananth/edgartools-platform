# The store counts the sessions a step opens

Status: open
Type: task
Owner: claude (operator, 2026-11-27: "everything should be dynamic code it in the skill nothing is fixed but nothing is wasted")

On `aws-20261127` the one-document step `gleif` (8 declared workers, the store's whole limit) was ready at 17:48:48 ET and
started at 18:09:49 ET: each worker freed went to a smaller step first. Once running, it was charged 8 of the store's 8
workers while the database showed 2 of its sessions, both idle (18:17 ET), reading its one file on one core.

## 5 whys

1. `gleif` waited 21 minutes: it needed 8 free store workers and smaller steps took each one as it freed.
2. It needed 8: a one-document step's floor is all its declared workers, since a move would abandon its document.
3. The store was "full": it counts each running load's declared `--workers`, read from the process listing.
4. Declared workers are not what a step uses: `gleif` held 2 idle sessions while charged 8.
5. Nothing measures the sessions a step opens, so the limit is spent on numbers written in a file.

## Checklist

- [x] The controller reads each step's sessions at work (`step_sessions`, the status's own reading: active or in a transaction, `application_name` `chain-<step>`) and keeps each running step's peak in its current start (attempt or move) beside the state file (`record_sessions`, `<state>.sessions`); a reading that fails keeps nothing (2026-11-27 18:24 ET)
- [x] The store charges a running step its measured peak once read twice, else its declared workers (`session_charges`, `workers_in_use(listing, charges)`); admission (`attempt_loop`), the controller, the local scheduler (`auto`) and the store line use the same charges (2026-11-27 18:24 ET)
- [x] A one-document step waits for one free store worker, not all of them, and starts with all its workers (`admit`'s `store_floor`); a store gone over sheds the movable steps through the existing `store_level` and `choose_move`, which never move a one-document step (2026-11-27 18:24 ET)
- [x] Tests that fail on today's code: `test_a_running_load_is_charged_the_sessions_it_was_measured_to_open_once_read_twice_else_its_declared_workers` (TypeError: `workers_in_use()` takes 1 positional argument), `test_the_controller_keeps_each_running_steps_peak_sessions_in_its_attempt_and_a_new_attempt_starts_again` (no `record_sessions`), `test_a_one_document_step_starts_with_all_its_workers_once_the_store_has_one_free` (Failed: it waited); with the change, load jobs and load monitoring 299 passed, skill lints 46 passed (2026-11-27 18:24 ET)
- [x] HOSTED-LOADS "Balancing a load" states the measured charge; data-operations' handshake already points at that section (2026-11-27 18:24 ET)
- [ ] Live: the charges read on a running load (the next hosted load: the store line's workers in use against the declared sum)
- [x] `/code-review` (Standards, Spec, GoF; `risky-reviewer` on Sonnet). GoF: leave it. Fixed: a peak of an earlier start was still charged after a move (charges now match the step's current start: the moved-start case in `test_the_controller_keeps_each_running_steps_peak_sessions_in_its_start_and_a_new_start_is_measured_again`); a one-document step admitted at full size forced sheds before it was read (shedding now charges a step once read once, admitting and raising after two); the failed-read claim had no test (`test_a_sessions_reading_that_fails_keeps_the_peaks_and_counts_no_reading`); `record_sessions` named one writer where `auto` also writes. Found in a touched function: `auto` overwrote the store's `left` with the minutes left every tenth cycle, which then bounded raises; the projection no longer reuses the name. Load jobs and load monitoring 300 passed (2026-11-27 18:24 ET)
- [x] Noted, not changed: a step quiet at its two readings (reading its file) is charged little, and its sessions opened later count from the next cycle; the store's half of memory kept spare covers that cycle (HOSTED-LOADS) (2026-11-27 18:24 ET)
- [x] Learning → skill: data-operations HOSTED-LOADS "Balancing a load" (the store counts the sessions a step opens; a step's `workers` is a cap and a first guess) (2026-11-27 18:24 ET)
