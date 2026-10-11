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
- [x] One limits module (`edgar_warehouse/mdm/clean/limits.py`): request and proposal bytes, records per batch, records-file bytes; every Python site reads it; a test checks the SQL functions' numbers equal it (`tests/mdm/test_clean_limits.py`, 4 pass, including the deferred-record bound). `company_prepare.py`'s `--limit 1..1000` stays: L4 rewrites that file. `consumer.py`'s 1..1000 is a page size, not a batch bound. 2026-10-10 21:17 ET
- [x] Migration: a match proposal stores `effects_sha256` (sha256 of the jsonb text of `effects`) in place of `effects`; `save_batch` compares the request's hash to it, and still compares `effects` for a proposal stored before; the 16 MB bound applies to the stored body. Tested on a populated store (a stored old-form proposal applies after the migration; a changed request against one is refused): `013_proposal_effects_hash.sql`, `tests/integration/test_clean_proposal_size.py` 6 pass. A proposal recorded before and recorded again after is refused as a digest collision and assessed again (header). 2026-10-10 21:17 ET
- [x] `mdm.prepare` cuts a batch by a records byte budget (1 MiB) as well as by count (`_batches`, tested). Batch ids and file names now count batches (`:{n}`): unchanged for an input cut by count only; different where the byte cut applies, so a re-prepared input gets new ids (rebuild is the only system). 2026-10-10 21:17 ET
- [x] The Stage measures a batch's request before any SQL and refuses one over `limits.REQUEST_BYTES` with its size and the remedy (Spec review: otherwise the bound is still met only at the end); tested. 2026-10-10 21:17 ET
- [ ] Company preparation (`company_prepare.py`, one batch of up to 1,000 records) cuts by the same byte budget: on L4's branch, which rewrites that file
- [x] Real records at scale: the installed proof on this branch (old landed SEC bundles and the Golden Copy's GLEIF records) masters without a size refusal. Passed 2026-10-11 00:55 ET in 25 min 59 s: 6,414 Companies; GLEIF 3,716 records, 3,052 bound (2,861 `sec-gleif-name-jurisdiction`, 191 `sec-gleif-name-postal`); bindings `9216cc18…`, equal to the checkout replay; a killed worker's item verified on attempt 2; the second pass changed nothing. Report `evidence/installed-company-proof-20261011.json` sha256 `79943859…`
  - [x] Two earlier runs failed in the GLEIF read with a redacted database error: the Mac slept mid-read (power log: sleep 23:34 and 00:09 ET), so the worker's lease lapsed and its write was refused. The passing run kept the machine awake (`caffeinate -dimsu`). Long local proofs need it. 2026-10-11 00:30 ET
- [x] CI: all six checks green on `95131ea3` (one engine test patched a removed alias; it now sets `limits.RECORDS_FILE_BYTES`). 2026-10-11 00:38 ET
- [x] Affected tests locally: 218 MDM Postgres integration tests (217 passed, 1 xfailed) and 822 MDM and engine tests on the first commit; after the review fixes, 80 proposal, core, merge-worker and binding Postgres tests and 4 limits tests pass. One test read stored `effects`; it now takes them from `assess`. 2026-10-10 21:17 ET
- [x] Three-axis review: GoF "leave it" (limits as plain constants, test holds SQL equal); Standards: 013 correct against 001, judgement calls fixed (each limit its own name, messages from the constants, aliases removed, retry-across-migration noted); Spec: early request check added, deferred bound tested, old-form refusal tested, Company preparation moved to L4. 2026-10-10 21:17 ET
- [x] PR #906 merge on the operator's word: "merge one by one", 2026-10-11 06:40 ET; CI green on `61fd35fe`
- [ ] L4's installed proof reruns on top: 6,414 Companies, 3,052 GLEIF bindings, bindings `9216cc18…`
