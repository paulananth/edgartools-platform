# 246: The second Securities batch is recorded in the Change Journal

Type: task. Status: open. Blocked by: none. Found by the rerun check (operator, 2026-11-16: "Need to check if change journal working as expected if you run again no database updates"; "Decision for you: yes").

## Question

Does a second full run of the load chain change nothing in the hosted store?

## Evidence

Rerun of all 41 steps (08:38 to 08:41 ET, 2026-11-16), row counts of all 84 tables before and after:

- 79 tables identical (MDM, silver, Change Journal, RDM, Rules); the highest golden record change number unchanged.
- 40 steps printed `0 documents loaded, N already loaded before`.
- `nport-security-other-keys` loaded its 1 document again: 1 run and 3 unit rows in Bookkeeping, nothing in MDM. Its target had `record: false`, so it wrote no Change Journal record, and every run loaded it. A file's processing identity already holds its target, so the first batch's record could not have skipped it.

## Parts

- [x] 2026-11-16 09:24 ET The target `mastering_other_keys` of `sec.nport.security` loses `record: false`: it gets the `processed` step and the `journal.delivered` check. Failed before: `test_the_second_batch_of_securities_is_recorded_and_a_second_pass_skips_it` (`KeyError: 'processed'`) and `test_a_target_gives_its_recorded_steps[sec.nport.security/mastering_other_keys]` (steps and checks differ); both pass now. Mapping Document regenerated (`rules mapdoc check` clean).
- [ ] Hosted: the next chain run loads the source's files once more (its rules changed, so every file is processed again under the new identity), then a second run changes nothing, counted as the rerun above did. Not run: it reloads the N-PORT securities.
- [x] 2026-11-16 09:24 ET Bookkeeping skill: what `record: false` does.
- [x] Learning → skill: `bookkeeping` SKILL, "Writing a target": `record: false` means the target loads every file on every run.
