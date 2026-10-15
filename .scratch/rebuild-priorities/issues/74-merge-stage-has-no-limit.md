# The Merge Stage has no limit

Priority: 74, tier 1, in flight (raised by the operator, 2026-10-14). Map: [Rebuild priorities](../map.md).

Type: task (code). Status: claimed (Claude, 2026-10-14 ET, branch `claude/merge-no-limit`). Blocked by: none. Blocks: ticket 01's ownership Proving Run.

## Why

The ownership Proving Run (ticket 01, 2026-10-13 20:55-21:14 ET) stopped in its first pass: "Affected closure exceeds bounded replay budget". The Merge Stage replays a batch with everything it is connected to, and its closure follows links both ways: an owner's record pulls in its issuer, the issuer every other owner that links to it. The cohort's insider network (8,272 owner records, 1,706 issuers and their decisions) is one group, past the 10,000 cap. The same cap made Form ADV keep custodian links out of MDM.

Operator, 2026-10-14: "Fix the Merge Stage (Recommended)" (a link pulls in only its target's own records unless the batch changes the target's identity), then "merge stage should have no limit".

## What "no limit" covers

- **Removed: every refusal by size.** The closure cap (10,000 records, decisions and identities), the projection retirement and projection caps, the assessment history cap, the save request's 16 MiB cap and the match proposal's stored and sent byte caps, in Python (`merge.py`, `limits.py`) and in SQL (a new migration replacing `write_batch`, `preview_batch` and `record_match_proposal` without them).
- **Kept: how the input is cut.** `mdm.prepare` still cuts a run's records into batches of at most 1,000 records and 1 MiB (`limits.batches`); that divides the work and refuses nothing, and the batch's own assertion, decision and deferred counts stay checked against it.
- **Then, if the replay is slow:** narrow the closure (the operator's first answer) as speed work.

## Checklist

- [x] GoF consult on `merge.py`'s closure and the limits: leave it; the limits were gathered in one module by #906 and this change only deletes (2026-10-14 07:10 ET)
- [x] Remove the size refusals in Python; the closure and projection queries unbounded: `merge.py` (no `closure_limit`, no `LIMIT :lim`, no request refusal), `limits.py` keeps the input cut and the worker file bounds, which grow with the input only (2026-10-14 07:10 ET)
- [x] A migration replacing the SQL functions without the byte caps: `019_merge_stage_no_limit.sql` (`write_batch`, `record_match_proposal`, `match_proposal_snapshot`, each its latest body less the caps), registered in `store.MIGRATIONS`; `test_clean_limits.py` holds that none has a size cap (2026-10-14 07:10 ET)
- [x] Tests: a closure past 10,000 loads; a proposal past 64 MiB and a save request past 16 MiB are stored; 12 passed on PostgreSQL 16 in Docker (2026-10-14 07:10 ET)
- [x] Living docs: data-platform SKILL (`distinct_on`), candidate-assessments spec; dated reviews and ADRs left as written; the three stale `limit=` callers in `test_clean_lookup_indexes.py` fixed (2026-10-14 08:05 ET)
- [x] Operator, 2026-10-14: "eventually we will be using snowflake postgress or databricks lakebase postgress do not design for local postgress limitation": no cap here is chosen for a local machine (2026-10-14 08:05 ET)
- [x] The no-limit ownership run measured: 23 batches in 60 min, `mdm.batch` 49 MB; each batch replays and rewrites the whole insider network. Stopped; the replay is narrowed (operator, 2026-10-14 08:21 ET: "Design it for speed ... make sure Postgres is as efficient as possible") (2026-10-14 08:21 ET)
- [x] GoF consult on the narrowing: one finding: the batch's scope is computed in three places (closure, snapshot, retirement) and changed in 6 of the last 12 commits; `load_closure` returns one `Closure` that all three use. `_execute` otherwise left (2026-10-14 08:21 ET)
- [ ] ~~The closure in two classes: full (a batch's records, decision anchors, hierarchy links both ways: readings by record and by incoming link) and own (a plain link's far end: readings by record only); only keys not yet read are read each round~~ deferred to ticket 77: the operator chose a merge record by record ("Option 1", 2026-10-14) over narrowing the closure
- [ ] ~~Write-back only the batch's scope: full entities, relationships touching them, reviews about them; old relationships and reviews retired only in scope~~ deferred to ticket 77: the operator chose a merge record by record ("Option 1", 2026-10-14) over narrowing the closure
- [ ] ~~The snapshot carries the same scope (`own`); a scope without `own` hashes as before; a mutation test per kind of row the batch overwrites or retires makes the proposal stale~~ deferred to ticket 77: the operator chose a merge record by record ("Option 1", 2026-10-14) over narrowing the closure
- [ ] ~~Every lookup uses its index: readings by record, `master_entity` by uuid, the retirement lookup as joins (no `= ANY` under `OR`), the snapshot's own branch; checked with sequential scans off~~ deferred to ticket 77: the operator chose a merge record by record ("Option 1", 2026-10-14) over narrowing the closure
- [ ] ~~Old against new: an ownership slice and the GLEIF fixtures through `904f7318` and through the new code: current records and Company rows equal~~ deferred to ticket 77: the operator chose a merge record by record ("Option 1", 2026-10-14) over narrowing the closure
- [ ] ~~Known cost left: when an issuer is itself in a batch, every owner linking to it is read as own; if it shows, read own ends' stored projections instead~~ deferred to ticket 77: the operator chose a merge record by record ("Option 1", 2026-10-14) over narrowing the closure
- [ ] ~~The ownership Proving Run reruns: both passes, time per batch measured~~ deferred to ticket 77: the operator chose a merge record by record ("Option 1", 2026-10-14) over narrowing the closure
- [ ] ~~Three-axis review~~ superseded: ticket 77 rewrote the same code (closure, write-back, the proposal's save) on top of this change, and its three-axis review covered the result (2026-10-14 12:29 ET)
- [x] The full installed proof (a Merge Stage change), on main after #960 and #963 (`e3a968ca`): the installed empty-store Company proof (`.planning/workstreams/whole-source-census/installed_proof.py`), 27.7 min: 6,414 Companies, 3,052 GLEIF records bound, decisions by rule CIK 6,414 / name and state 2,861 / postcode 191, open reviews as on 2026-10-11 (664 / 312 / 39), bindings equal the pinned replay (9216cc18…), a killed worker resumed, the second pass changed nothing (2026-10-14 12:54 ET)
- [x] PR, CI green, merge on the operator's word: #960 merged as `9da59e01`, operator 2026-10-14: "Merge pending pR" (2026-10-14 12:29 ET)
