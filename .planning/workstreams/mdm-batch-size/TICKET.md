# MDM batches never fail on size at the end of a run

Operator, 2026-10-10 ("this has happened many times, how do we permanently fix it"; "ok continue with the plan").
Branch `claude/merge-size-split`, worktree `../edgartools-platform-claude-merge-size`. Blocks Issue 20 L4's full proof.

## Finding

- The installed Company proof failed at the GLEIF `mdm.merge`: the match proposal was 19.7 MB, and `mdm.record_match_proposal` refuses a body over 16 MB (`001_mdm.sql:893`). 2026-10-10 20:35 ET
- How a batch grows (SEC chunk 1, 919 records): records file 1.4 MB, save request 6.1 MB (x4.4), match proposal 9.6 MB (x7). GLEIF: 1,000 records of about 1.9 MB, proposal 19.7 MB (x10)
- Cause: the proposal stores the whole save request twice, as `command` and as `effects` (`merge.py:800-820`); `effects` is read only by `save_batch`'s equality check (`001_mdm.sql:547`) and the shape check (`:905-907`). Batches are cut by count (1,000), never by bytes, and the 16 MB and 1,000 limits are copied by hand into about 10 places
- Time: mastering a 919-record batch is 87% database (`save_batch` 6.3 s, `preview_batch` 5.7 s, each over the 6 MB request), 13% Python; a Rust rewrite would not change either the time or the failure (`.scratch/l4-rust/research.md` on the L4 branch)

## Parts

- [x] GoF consult: the shape is right; keep stored proposals that still hold `effects` valid; one place for the limits, plus a test that the SQL uses the same numbers. 2026-10-10 21:01 ET
- [ ] One limits module (`edgar_warehouse/mdm/clean/limits.py`): request and proposal bytes, records per batch, records-file bytes; every Python site reads it; a test checks the SQL functions' numbers equal it
- [ ] Migration: a match proposal stores `effects_sha256` (sha256 of the jsonb text of `effects`) in place of `effects`; `save_batch` compares the request's hash to it, and still compares `effects` for a proposal stored before; the 16 MB bound applies to the stored body. Tested on a populated store (a stored old-form proposal applies after the migration)
- [ ] `mdm.prepare` cuts a batch by a records byte budget as well as by count
- [ ] Test: a batch of the largest real records at the budget masters without a size refusal (SEC and GLEIF shapes)
- [ ] Affected tests locally (testmon plus the migration and MDM Postgres tests by name)
- [ ] Three-axis review (Standards, Spec, GoF), PR, CI green, merge on the operator's word
- [ ] L4's installed proof reruns on top: 6,414 Companies, 3,052 GLEIF bindings, bindings `9216cc18…`
