# 199: Rebuild mastering on three operations

Priority: 199. Map: [Rebuild priorities](../map.md). Opened 2026-11-06 10:18 ET (operator: "yes open the rebuild ticket and start"). Follows ticket 197, which holds the prototype's results.

Type: task. Status: open. Blocked by: none.

## Question

How does production mastering become the three operations (extract, load a batch to a merge stage, merge finds or creates the id), keeping what production needs, and at what cost for each thing added back?

## Method

One item at a time, built, compared with the engine and timed, as in ticket 197. Seven wastes first (operator: "always remember 7 wastes"): before moving or deleting a step, name the waste it removes and how it stays gone. Merge logic stays in the shared Rust and Python; store access stays plain, behind one layer, on PostgreSQL and MySQL. Relationships are not part of mastering (operator, 2026-11-06). They run after mastering, with or after the silver write, from the list each stored record carries.

The prototype is local scratch at `~/edgar-local-tmp/company-proto/` (`merge3.py`, `store.py`). Measurements run on mains power: a sleep at 1% battery hit one load.

## Item 1: reviews and steward actions, on the prototype

The store holds 458 open and 194 retired `binding_required` reviews and no master in review. It holds 778,637 binds, 11 merges and no steward decision, so steward cases are invented decisions on real records.

| Case | PostgreSQL | MySQL |
|---|---|---|
| Open waiting reviews, either source order | 458 of 458, same record and version | 458 of 458 |
| Exclude 1 of 11 pairs | 10 merges, 1 kept apart with a review | The same |
| Override one field | 1 of 8,361 masters changes, ids kept | The same |
| Revoke the override | 8,361 of 8,361 back to the same | The same |
| Reverse every merge, then deliver again | 0 merges re-form | The same |
| The engine's own binds and merges, reversed by the prototype, against Rust replay | 22 of 22 masters | Not run |

Each record keeps the master it was first bound to, so a reversal returns it there. Closed reviews differ from the engine's because they depend on arrival order. After a merge, the engine binds the linking record to the lowest id of the pair (11 of 11), not by any business rule, so a run compared from scratch differs on which side that record ends; only 10 of 22 groups match that way, which is why the seeded test is the proof.

No steward decision means one extra indexed read a batch: Company took 24.0 to 28.6 s under load against 22.9 s before, which is within the noise.

Not covered: chained merges reversed in dependency order, quarantine, reviews from a master conflict (none in the store), and `override_source_disagreement` is counted but not stored.

## Items 2 and 3, on the prototype

**Matching is the engine's own.** Withheld values live in `plan_record_matches` and `link_matching_records`, so the prototype now calls those two Rust functions around plain lookups, and its own grouping and per-source merge list are gone. The rule decides conflicts, merges and exclusions, and a linking record binds as the engine binds it. `group_batch_records` from ticket 197 has no caller left and is deleted.

| Check | Result |
|---|---|
| A CUSIP and ISIN on two Securities, invented records under the real `nport-security-cusip` rule | Binds by the CUSIP; the ISIN stays withheld and with its own master; delivered again, no change |
| Company | 67,034 of 67,034 fields, 3,258 of 3,258 name matches, 458 of 458 open reviews |
| 50,000 whole Security masters | 50,000 same members, 199,760 of 199,760 fields |
| The 11 stored merges | 11 of 11, 44 of 44 fields |
| Exclude 1 of 11 pairs | 10 merges, 1 kept apart with an `excluded_consolidation` review |
| The engine's merges reversed by the prototype, against Rust replay | 22 of 22 masters |

| 99,070 Security records, back to back, a load also running | Run 1 | Run 2 |
|---|---|---|
| Own grouping | 166.1 s | 190.3 s |
| The engine's matching | 189.7 s | 298.5 s |

So the engine's matching costs roughly 15 to 55% more here, mostly in the id lookup; the spread is too wide to say more until the machine is quiet. It is kept because one rule in one place is worth it. No record in the store has a withheld value, so a real case waits for `sec.nport.security`. Steward cases on these functions ran on PostgreSQL only.

**Set-aside records** go through one plain table: 152,557 of 152,557 equal the engine's reviews in id, source, reason and blocking flag, at a median 0.135 ms a record.

## Item 4: delivery to readers, on the prototype

Nobody reads what is stored for delivery today.

| Measured on the shared store | Result |
|---|---|
| Outbox rows | 7,524 for `journal`, `export` and `graph`, all `verified = 0` |
| Payload bytes held | 10.6 GB (2.1 GB on disk) |
| MDM events in the Change Journal | 0 of 177,813; the rest are `file.processed` and `work.verified` |
| Load steps that run `mdm.publish` | 0 in `rules/` |
| Batch and proposal tables | 18.5 GB, against 1.0 GB of current masters |

Real readers pull: silver through `MdmIds`, others through `consumer.py` pages at a fixed generation. So the prototype stores no payload. Each master keeps the file that last changed it, and a reader asks what changed after its checkpoint.

| Test on Company | Result |
|---|---|
| Read after 6 of 15 files, then after the rest | The reader's copy equals 8,361 of 8,361 masters |
| Every file delivered again | 0 masters reported changed |
| A crash mid-run | The reader never saw the rolled-back file |
| Masters against the engine | 67,034 of 67,034 fields |

Search stays an owner build after a load (ticket 196), reading current masters, so it adds nothing to a merge. Its name index took 0.11 ms a master on 8,361 masters. The lookups the engine writes per record are not all compared here. MySQL is not run for this item.

Decision for the operator: `required_consumers` in `rules/merge/policy.yaml` still asks for all three payloads, and `docs/` still describes `mdm publish` to Snowflake and the graph. The rebuild stops writing them only on the operator's word.

## Item 5: database-side safety, on the prototype

One lock row per kind (`SELECT ... FOR UPDATE`), held for a whole file, replaces leases and fences on both engines. The file's row sits in the same transaction, and the store is read again under the lock, so a writer works from current state. If a writer dies, the database rolls back and frees the lock.

| Test on Company | PostgreSQL | MySQL |
|---|---|---|
| Two writers at once, opposite order | 67,034 of 67,034 fields; no identifier on two masters | The same |
| `kill -9` mid-run, then resume | The same; no file half done | The same |
| Runtime login: read, write masters, add a decision | Allowed | Allowed |
| Runtime login: delete or change a decision, drop a table, add a column | Refused | Refused |

Items 2 to 4 also ran on MySQL on the final version: withheld, the 11 merges, the exclusion and the reader. Serial writing per kind loses parallel bundles of one kind; at this speed that costs less than the conflicts it removes. Company on the final version took 37.0 s while a load ran, against 22.9 to 29.2 s before the lock, so the lock's cost is not yet separated from the load's. This is proof on a prototype, not the skill's full engine qualification.

While these tests ran, OpenFIGI bundle 15 stopped on `expired_destination_authority`, the fault this design has no lease to hit.

## Side research: OpenMetadata as the steward tool

Operator, 2026-11-06: "can openmedatate can be a steward tool to review and merge". From its public documentation, not tried here. It has Tasks and reviewer approvals, documented for glossary terms and asset metadata, and custom properties on existing types. No master record merge was found, and a feature request says user-defined entities are unsupported. So it can show work to a steward, but the merge stays in MDM. Parked (operator, 2026-11-06: "park the openmetadata now"). Not built: OpenMetadata work belongs to Codex.

## The move to production

Operator, 2026-11-06: "yes" to replay and replace. There is no live system to protect and every record and decision is stored, so the new path is built beside the old one, replayed, compared and switched, with no flag and no dual running.

1. `edgar_warehouse/mastering/`: the prototype as a reviewed package with matrix tests.
2. One real load: `load` merges N-PORT registrant through it.
3. `mdm rebuild`: replay every stored record and compare with the old masters.
4. Readers move: `MdmIds`, `consumer.py`, `steward split`, the search build, and relationships with the silver write.
5. Delete the old path.

Dropped, since nothing uses them (operator, 2026-11-06: "why do i even need ... isnt it not over engineering"): the history table, quarantine, chained reversals and a full engine qualification. The same tests on PostgreSQL and MySQL stay, in the CI jobs that exist. A feature stays only if a reader, a command or a stored record uses it. The `journal`, `export` and `graph` payloads stop (operator: "1 yes").

Stage 1 result: 9 tests pass on PostgreSQL and on MySQL, and the package on all 14,024 real Company records gives 67,034 of 67,034 fields in 35.8 s. A zero-padded identifier in a test exposed a bug every real replay had hidden: lookups used the raw form, where the store keeps the normal form, and would have made a duplicate master.

## Checklist

- [x] Reviews and steward actions on the prototype: waiting reviews, exclusions, overrides, revokes and reversals, on PostgreSQL and MySQL (2026-11-06 10:32 ET).
- [ ] ~~Chained reversals and quarantine~~ deferred to none: dropped, nothing uses them.
- [x] Stage 1: `edgar_warehouse/mastering/`, 9 tests on both engines (2026-11-06 11:48 ET).
- [ ] Stage 2: one real load through the package.
- [ ] Stage 3: `mdm rebuild`, every record replayed and compared.
- [ ] Stage 4: readers moved; relationships with the silver write.
- [ ] Stage 5: the old path deleted.
- [x] Withheld values on the prototype, by the engine's matching (2026-11-06 11:03 ET).
- [ ] Withheld values on real `sec.nport.security` records.
- [x] Records set aside by classification on the prototype, 152,557 of 152,557 (2026-11-06 11:03 ET).
- [x] Delivery to readers on the prototype: a reader pulls what changed after its checkpoint; no payload is stored (2026-11-06 11:29 ET).
- [ ] Operator's decision: stop writing the `journal`, `export` and `graph` payloads, given that none is read.
- [ ] `consumer.py` and `MdmIds` on the new tables, and the rest of the per-record lookups.
- [x] Database-side safety on the prototype: one lock per kind, a real kill, two writers, a restricted login, on both engines (2026-11-06 11:29 ET).
- [ ] Database-side safety in production code, through the storage adapter, proved equal before the old routines go.
- [ ] The thin slice: one source from load to reader, in the repo, on both engines.
- [x] Rule which rules allow a merge from the rule itself: the engine's matching does (2026-11-06 11:03 ET).
- [ ] Survivor by `published_at` then id, as replay does.
- [ ] Bookkeeping per file, not per batch; the `processed` step; what the step around the silver writer costs.
- [ ] Person and Fund on MySQL; OpenFIGI at full size on the final version.
- [ ] The rebuilt path on every source, compared with the engine; the old path deleted.
- [ ] Parts from ticket 197: the catalog read in every bundle; the cost of a step whatever its work; bundles that share keys; deadlocks in claims; the batch document stored and compared many times; a resumed run stepping over retained batches; why a stored bundle is loaded again.
- [ ] Learning → skill.
