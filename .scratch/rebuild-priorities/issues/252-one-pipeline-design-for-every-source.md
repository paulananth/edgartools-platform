# 252: One pipeline design for every source

Type: task. Status: open. Blocked by: none.

## Question

Do the 17 sources' pipelines follow one design? Where they differ, is the difference in the data or only in how the pipeline was written?

## Method

Every `rules/sources/*/source.yaml` was expanded to its steps (`rules.shape`) and laid in one table: 17 sources, 27 targets, 41 chain steps (`rules/load-chain.yaml`). Each difference was then checked in the code that reads the setting. Counts only.

## What is already one design

- Every target is written in one shape (extract, master, silver) and expands to the same step kinds, checks and leases.
- 25 of 27 targets run at grain `run`; all 25 loading targets end in a Change Journal record.
- All 16 Bookkeeping sections are version 2; every target carries the same three run checks.

## Findings and goals

| # | Finding (verified) | Goal |
|---|---|---|
| 1 | **The links table is rebuilt whole 11 times in one fresh load.** 5 targets carry the build step; the chain runs them 11 times, and each build reads every stored record. 3 sources that state links (Form ADV, OpenFIGI, ownership) carry no build, so their links show only because a later step in the chain happens to build. Loaded alone (a daily run, the planned OpenFIGI reload), their links stay missing. | The links table is built once per load, after the last merge, in one place (the chain's finish, beside the lookups). A source loaded alone builds it too. No target carries the step. |
| 2 | **Two targets still run by the unit** (the N-PORT Security mastering and its other-keys target): one reads the other's step from another run, which a run at grain `run` cannot do. They alone keep units, leases, a heartbeat and lease override (60 s, 900 s) and all of the by-the-unit recovery text in the skills. | Every target at grain `run`. Either fold the two into one target, or let a run read a finished run's output by its receipt. Then delete the by-the-unit path from the loader and the skills. |
| 3 | **`local: true` does nothing** on the 2 targets that set it (OpenFIGI and SEC Company mastering): `rules/local.py` and `bookkeeping/clean/config.py` both return before reading it when the grain is `run`. The SEC Company file still explains it in a comment. | Remove the setting from both targets, and from the code once finding 2 leaves no target by the unit. |
| 4 | **A lease and heartbeat on a target at grain `run` has no reader.** The registration capture target sets 300 s and 30 s; a run at grain `run` holds no lease. | Remove them; the validator refuses lease settings on a grain `run` target. |
| 5 | **The same captured files are read again for each target of a source.** Form ADV reads its custody file in 3 targets; ownership reads the same filings in 2; 13F in 2; N-PORT Security reads 2 of its files in 2; the N-CEN submissions file is read by 4 sources in each of 4 quarters. The one shape already lets a target master and land silver from one read. | One target per source reads once, then masters and lands silver ("pipeline must complete both mdm and silver together"). A second target stays only where it is a second publication. Measure the read time saved first. |
| 6 | **A delivery's identity is a different fact in each source**, each typed by hand into the chain: `publication_count` (GLEIF), `published` (Form ADV), `period` (N-PORT Security), `observed_at` with 3 more (SEC Company), `ticker_file_date` (OpenFIGI), and none for N-CEN, which uses only the `revision` number. A daily run must edit the chain file. | One convention: a delivery states its date once, read from the capture's receipts where the capture holds it; `revision` follows from it. No date typed into the chain. |
| 7 | **"workers" means two things.** `execution.workers` in a source file is threads inside one read (1 or 2; one source sets 2). `--workers` on a load is processes per step. | One knob. Measure whether the second thread gains anything on the one source that sets it; if not, delete `execution.workers`. |
| 8 | **How files arrive is declared 3 ways.** 4 sources declare `acquisition`; 2 of them have a capture target (one copies, one fetches); 13 sources declare nothing, so the rules do not say where their files come from. | Every source says how its files arrive in the same place, or capture is ruled outside the pipeline and the 2 capture targets and 4 sections move out. Operator's decision. |
| 9 | **A stopped load at grain `run` reads its files again from the first step** before the Change Journal can skip a merged batch (measured on the largest file: about 15 minutes before any merge resumes). | A restart skips a read whose output file is already written with the same input hash: the receipt is the proof. |

Lower value, same cause (written at different times):

- The prepare step is named `records` in 2 sources and `prepare` in the rest; one source suffixes every step `_security`; target names mix hyphen and underscore (`subfund-pairs`, `security_symbols`).
- Source files carry about 126 comment lines that cite tickets and dated rulings; version 1.0 keeps no history in rules files.
- The chain gives every step its own `workers`, `bundles`, `minutes` and `attempts` by hand; 37 of 41 are `workers: 2, bundles: 1`.

## Order

Findings 3 and 4 are deletions with no data effect: do them first. Finding 1 removes ten whole rebuilds from every fresh load and fixes a wrong result for a source loaded alone: next. Findings 2, 5 and 9 change how long a load takes: measure one source before changing all. Findings 6, 7 and 8 need a ruling on the convention.

## Parts

- [x] 2026-11-16 16:45 ET Every source's targets expanded and compared; each finding checked in the code that reads the setting (this file).
- [x] 2026-11-16 17:23 ET Finding 3: `local: true` and its comments removed from the 2 targets (PR 1846; `test_no_target_at_grain_run_names_a_setting_it_does_not_read`).
- [x] 2026-11-16 17:23 ET Finding 4: the lease settings removed; the validator refuses them at grain `run` (PR 1846; `test_a_target_at_grain_run_refuses_what_only_a_target_held_by_the_unit_reads`). The processing identity now leaves out how a target is held.
- [x] 2026-11-16 17:23 ET Finding 1: `silver links` builds the table once; a `load` alone builds it after its last bundle, the chain once in `--finish` (`--no-links` on each step); the 5 targets carry no step and the worker no longer builds links. Nine waits that existed only for link order are gone from the chain. Tests: `test_the_chain_builds_the_links_table_once_after_the_loads_and_no_target_builds_it`, `test_a_load_that_mastered_records_builds_the_links_table_once_after_its_last_bundle` and 4 beside it, `test_links_land_as_one_row_a_period_and_a_second_build_keeps_them` (PostgreSQL).
- [ ] Hosted: findings 1, 3 and 4 move the processing identity of 8 sources once, so their files load again on their next load. One reload after the remaining findings land, on the operator's word.
- [x] 2026-11-16 17:23 ET Operator, 2026-11-16: "6 and 8 agreed now fix the inconsistency". Finding 6: one delivery-date convention, read from the capture. Finding 8: my reading is one place where every source says how its files arrive; to confirm before building.
- [x] 2026-11-16 21:17 ET Finding 2, first half: all 27 targets at grain `run`. The second N-PORT Security batch reads the same files itself with its own context (`extract: [{file: record.yaml, context: {batch: other}}]`), so no target reads another run (`test_every_target_is_at_grain_run`, `test_the_second_batch_of_securities_reads_the_same_files_with_its_own_context`). Cost: that quarter's files are read twice, once per batch; finding 5 removes the second read.
- [ ] Finding 2, second half: delete what no target uses now: the read of another run's step (`pieces: {run: ...}`, `verified_units`), then the by-the-unit path (units, leases, heartbeat, `local`) from the loader, Bookkeeping and the skills.
- [ ] Finding 5: one target per source reads once (measure one source first).
- [x] 2026-11-16 21:02 ET Finding 9: a run worked again keeps the reads it wrote (PR 1849; `test_a_stopped_run_worked_again_does_not_read_again_what_it_wrote`).
- [x] 2026-11-16 21:32 ET Finding 6: a target says where its delivery's date is read from the capture's file names (`delivered: {key, fact}`); the load fills the fact and takes the revision from the date. Declared on 10 targets of 6 sources (N-CEN x4, Form ADV, N-PORT Security); 40 typed lines left the chain, which now types no date and no revision for them (`test_a_delivery_takes_its_date_and_its_order_from_the_captures_file_names`, `test_no_step_types_the_date_or_the_order_of_a_delivery_its_capture_states`; read from 4 real local captures). `delivered` is no part of the processing identity: the fact's value already is.
- [ ] Finding 6, what no captured file states yet: OpenFIGI's ticker file date and its two revisions, SEC Company's capture time, and GLEIF's publication count (a count, not a date; its file name does carry the date). Each needs the capture to hold the fact first.
- [x] 2026-11-16 21:32 ET Finding 7: measured on the one source that sets 2 threads (13F securities, 52 local files, 149 MB, two rounds): 4.8 s with 1 thread, 2.6 s with 2, 1.9 s with 4. The second thread gains 1.8 times, so the setting stays; `data-operations` "One design" now says which setting is which. Folding it into `--workers` would move every source's processing identity: not worth a full reload for a name.
- [ ] Finding 8: operator's ruling on where capture is declared.
- [ ] Names, comments and chain defaults (the lower-value list).
- [x] 2026-11-16 16:45 ET Learning → skill: `data-operations` "One design" (the checks a new target must pass), and the skills pruned of by-the-unit detail that only two targets use, stale paths and narrative (same PR).
