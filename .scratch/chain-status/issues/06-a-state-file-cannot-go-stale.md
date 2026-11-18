# A chain state file cannot go stale: an old file is set aside, and a reset store is another store

Status: resolved
Type: task

Operator, 2026-11-18, when the scheduler refused to start on an old `chain-fresh-v2.log`: "This must not happen fix skills".

## Findings (five whys, from the code and the run)

- The run label is chosen by hand and `fresh-v2` had been used on 16 November; its file held done lines and no store marker, so
  `ensure_store` returned "unmarked" and the run stopped and asked. A file without a marker can only be from before markers existed,
  so asking each time is the wrong default: the safe action is to set it aside (never trust, never delete).
- The marker is the instance's address only, and a reset keeps the address: a label used again after a reset would have read the old
  file as "same" and skipped every step of the load on empty stores. A reset must make the file another store's.
- The database's creation identity (its `pg_database` oid) changes when it is made again, and any login can read it.

## Parts

- [x] A file with lines and no marker is set aside and kept, and the run goes on; `--adopt-state` still keeps one on the operator's word
  (2026-11-18 12:11 ET; `test_a_state_file_with_lines_and_no_marker_is_set_aside_and_kept_never_trusted_and_never_a_reason_to_stop`:
  `assert 'unmarked' == 'set aside'`)
- [x] The marker carries the database's generation, so a reset store is another store; an unreadable generation changes nothing, so a
  running load's file is never archived by a connection blip (2026-11-18 12:11 ET;
  `test_a_reset_store_at_the_same_address_is_another_store_so_a_reused_label_skips_nothing`:
  `TypeError: ensure_store() got an unexpected keyword argument 'generation'`; live: 7 digits read from the hosted store)
- [x] A generation read that fails returns nothing and never reports the connection (2026-11-18 12:11 ET;
  `test_the_database_generation_is_unreadable_as_an_empty_string_never_an_error_or_an_address`: `AttributeError: module 'load_chain' has no attribute 'database_generation'`)
- [x] A file made while the generation was unreadable (or before generations) learns it at its next start, so a blip at creation never
  leaves a later reset unseen; a file from before generations is trusted until then (2026-11-18 12:17 ET;
  `test_a_file_made_while_the_generation_was_unreadable_learns_it_later_so_a_reset_is_still_caught`:
  `assert False` on the file's last line ending with `generation 2002`)
- [x] `--status` shows the verdict the next run would give and does not count a file it would set aside, through the diagnostic login
  with the `mdm` database (2026-11-18 12:17 ET; `test_the_verdict_on_a_state_file_is_the_same_pure_answer_status_and_the_run_give`:
  `AttributeError: module 'load_chain' has no attribute 'state_verdict'`; live: the running load's file reads as this store's, 8 of 43 done)
- [x] The connection `database_generation` opens is closed (2026-11-18 12:17 ET; read in the PR)
- [x] The init runbook says a label can be used again and what sets a file aside (2026-11-18 12:11 ET; read in the PR)
- [x] Learning → skill: data-operations says a run label can repeat and a state file that does not name this store and generation is set aside, never a reason to stop; the init runbook holds the detail (2026-11-18 12:11 ET; the skill sentence, read in the PR)
