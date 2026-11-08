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

One lock row (`SELECT ... FOR UPDATE`), held for a whole file, replaces leases and fences on both engines. The file's row sits in the same transaction, and the store is read again under the lock, so a writer works from current state. If a writer dies, the database rolls back and frees the lock.

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

Stage 2 note: a load reads the approved rule version in the Rules Database, so a private copy of `rules/` is ignored. The first try ran the old merge and looked green; only reading the new tables showed it. The worker was then run on that load's real manifest, and the rule switch waits for stage 4. Each load check must read what was stored, not the run's state.

Stage 3 result: the mastering tables hold the same masters as the old path. The replay took 806,480 stored records; the N-PORT Security load kept writing 4,807 more while the comparison ran, which made its first counts differ (290 members, 186 with no master, 168 only new). Set beside those 4,807 records, 431,028 old masters match on members, identifiers and values, the other 4,797 hold those records, and all 435,044 new masters map to an old one. The 4,807 records, 5 of the 421 prepared batches, then went through the worker: 4,797 of 4,797 masters identical on members, identifiers, values, winners and conflicts, 781 new masters, 193 of 193 records set aside, 12.2 s. Waiting records are 458 on both sides. Set-aside records match on every replayed source. No identifier sits on two masters.

N-PORT Security by kind: all 421 batches were scored in 155 s without merging, and 5 were chosen for the rare cases (records reaching two masters, new masters, set-aside records, one ordinary batch). 4,534 records stored of 4,534, 466 of 466 set aside, 21 withheld ISIN values, 13.1 s, and a second run changed nothing. The rest of that load is not merged. The old load stopped at 15:11 ET after 3 h 16 min on `A rule's proposal no longer holds; re-assess`; its cause was not investigated, since that path is being replaced.

Relationships, checked against the captured 2026q2 N-PORT zip outside the pipeline (operator, 2026-11-06: "apply 7 wastes to relationships are they real and provable"). IS_SUBFUND_OF: 12,937 of 12,937 series and registrants are filed together. ISSUED_BY: 630 of 630 checkable CUSIP and LEI pairs are filed together; 2,216 more wait for a GLEIF record not loaded here. All 13,442 old links name one stored record that states them, and none is calculated. Of 794 claims whose CUSIP shows two values in the file, 790 are one LEI and an `N/A` the rule ignores, and 4 have two real LEIs and are waiting records. The 5 Security masters with two claims name one issuer each.

Links are a `relationship` silver table, one row a period, from a `silver.derive` build that follows the ruling that they run with or after the silver write. There is no MDM link table and no new operation. Stored records rebuilt 13,442 of 13,442 old links with equal periods, evidence and last-seen dates; the other 97 come from sample batches the old load never reached. On the shared store the build gave 13,539 rows in 19.0 s, verified, and a second run gave the same receipt. Rows show ISSUED_BY as `stated` until N-PORT Security is read under `sec-nport-security-v5`.

`--as-at` leaves with the history table. It was a real command, so "nothing uses them" was too strong for this one, and the operator decided it on that footing (2026-11-06, after its purpose was explained: "agreed no need"). `--as-of` stays for links, where it reads the stated periods; on one master it read a past generation, so that form leaves too and now refuses with a clear message. An audit of a past answer now means a replay of stored records under the same rule version.

## Checklist

- [x] Reviews and steward actions on the prototype: waiting reviews, exclusions, overrides, revokes and reversals, on PostgreSQL and MySQL (2026-11-06 10:32 ET).
- [ ] ~~Chained reversals and quarantine~~ deferred to none: dropped, nothing uses them.
- [x] Stage 1: `edgar_warehouse/mastering/`, 9 tests on both engines (2026-11-06 11:48 ET).
- [x] Stage 2: the `mastering.merge` worker on a real load's prepared manifest: 1,947 of 1,947 `sec.nport.registrant` records, each master with the engine's CIK and its record's fields, verified, 4.4 s against 59.3 s for the old merge step of that load (2026-11-06 12:10 ET).
- [ ] Point the Rules Database at `mastering.merge`, source by source: a load runs the approved version there, not `rules/` on disk.
- [x] Stage 3: `mdm rebuild`, every record replayed and compared: 431,028 masters match, and 4,797 of 4,797 for the records the old load stored late (2026-11-06 15:43 ET).
- [x] Review of stages 1 to 3 on Standards, Spec and GoF: two integer columns made BIGINT, a merge writes identifiers once, `compare` holds no transaction, `master_ids` deleted, the lock tested with two writers. The lock is one row for all kinds, not one a kind, since the changed-file number readers pull by runs across kinds; the prototype lines here describe one a kind. Without the lock the new test gives 400 masters for 200 (2026-11-06 15:47 ET).
- [ ] Stage 4: readers moved; relationships with the silver write.
- [x] Stage 4, facts rule: `facts.yaml` has its `execution` block, and a test passes every `source.read` contract through the worker's own check, PR 1475 (2026-11-06 18:30 ET).
- [x] Stage 4, retro checks: the guard runs `rules approvals check` when rules change, PR 1476; three skill rules, PR 1477 (2026-11-06 18:37 ET).
- [x] Stage 4, `context` on the mastering tables, PR 1478: 12 Apple questions, 7 the same as the old answers, 5 better, 0 worse (2026-11-06 20:07 ET).
- [x] Operator's ruling: name fragments are not stored. "use 7 wastes", to dropping them: 82% of lookup rows on the page measured; a search with no whole word scans the masters. The build fell from a projected 100 minutes to 6 on the local store, PR 1478 (2026-11-06 20:07 ET).
- [x] Operator's ruling: tests of code nothing calls are retired, not moved. "decommision un used tests use 7 wastes": the old search and detail scenarios, PR 1478 lists each claim and where it went (2026-11-06 20:07 ET).
- [ ] Measured 2026-11-06: of 393,674 Securities, only 164 come from OpenFIGI alone, so the setting removes few; N-PORT names the rest. Operator's ruling: a security is mastered only when a filing names it, and that is configurable. "agree with you recomendation but make it configurable". OpenFIGI adds to a master and creates none; 80% of security masters today are mortgage and municipal lines from it. Measure the count first; replay OpenFIGI under the rule.
- [x] Stage 4, unit A: `MdmIds` and `from_company` on the mastering tables; Apple's financial rows on its new master. Done 2026-11-06 23:30 ET: PR 1481; Apple's 25,135 facts, 437 line items and 760 measures sit on its new master, 0 on the old id.
- [x] Stage 4, unit B: every source's merge step on `mastering.merge`, CIK v2 in the same rule version, links with the silver step, `required_consumers` gone. No load runs before this version is active. Done 2026-11-06 23:30 ET: PR 1481; `rules test` passes, and the rule version is active on all 13 sources and merge/platform.
- [x] Stage 4, unit C: the remaining N-PORT Security batches on the new path, then links; Apple's first `ISSUED_BY`. Done 2026-11-06 23:30 ET: 421 batches merged in 18 min and verified; 55,320 links built (42,383 `ISSUED_BY`, 12,937 `IS_SUBFUND_OF`) in 7 min; AAPL has its `ISSUED_BY` to Apple, and 57 securities name Apple as issuer.
- [x] Rule tests on the new merge. Done 2026-11-06 23:30 ET: PRs 1485 and 1486. 13 test files moved; 2 stay on the bridge because they test the old engine, and leave in stage 5. Moving them found two gaps, fixed in 1485: only identifiers a rule minted could be found (153,031 tickers, SEDOLs and LoanX ids added to the local store), and the exact-name rule never ran.
- [x] Links at full size. Done 2026-11-06 23:30 ET: PR 1487. `add_review` was quadratic; the build ran 30 min unfinished, and takes 7 min with a set.
- [ ] N-PORT holdings in silver: 0 of 5,347,869 rows. All four figures reach 12 decimals against `DECIMAL(38,10)`. Waits on the operator: "10 is fine" means cut, round, or keep 12.
  - [x] The scale: DECIMAL(38,12), as filed (operator, 2026-11-08: "Scale 12, as filed"); 3,863,454 of 5,347,869 percentages carry more than 10 places. PR 1505, merged 2026-11-08 17:12 ET. The land: running locally.
- [ ] 198,808 reported links have no other end yet (`unresolved_endpoint`): measure why before stage 5.
  - [x] Measured 2026-11-08 17:10 ET: 199,597 are N-PORT ISSUED_BY, 1,239 others; 20,255 distinct issuers missing, two of them 45,851 and 19,746 links. Who those two are: not yet looked up.
- [ ] Steward revoke: the new merge has none, and PR 1485 removed its test. Waits on the operator: is it needed?
- [ ] Close the stale runs `bfe91575` and `61f32231`, after the holdings land.
- [ ] Stage 4, then: 13F, ownership and ADV from the existing files; the Apple chain from adviser to holding to AAPL.
  - [x] ADV June 2026: custodians mastered (494 records, 231 bound: 114 by LEI, 106 by broker-dealer number, 11 by exact name; 263 wait); `adv_custody` 3,022 rows, 3,022 with an adviser id and 2,541 with a custodian id. Verified by count, 2026-11-08 13:05 ET.
  - [x] 13F from the p07 files: 52 information tables, 10 managers; 283,725 holdings, 283,715 with a Security; 356 AAPL rows on the one AAPL Security, 355 with a manager (5 managers). Verified by count, 2026-11-08 13:15 ET.
  - [x] Advisers join the SEC Company holding their Item 1.D(3) CIK (operator: "Both"): rule iapd-adv-cik, filings as iapd.adv.filings.v2. PR 1503, merged 2026-11-08 17:04 ET. Real June file: 704 filings carry CIKs; 2,935 of 2,938 keep their master; 3 in review (advisers this store made from the CRD first).
  - [ ] The Schedule D 7.A RELATED_PERSON link (operator: "RELATED_PERSON (Recommended)"): PR 1506 committed; push waits on the operator's word past the guard.
  - [ ] The Apple chain from an adviser: March 2026 ADV names Hilltop Holdings (a 13F manager holding AAPL) by CIK; load March once PR 1506 merges.
- [ ] Stage 5: the old path deleted.
- [x] Withheld values on the prototype, by the engine's matching (2026-11-06 11:03 ET).
- [x] Withheld values on real `sec.nport.security` records: 23 ISIN values withheld across 10 chosen batches, and no identifier on two masters; the 5 batches of the old load gave identical masters (2026-11-06 15:43 ET).
- [x] Records set aside by classification on the prototype, 152,557 of 152,557 (2026-11-06 11:03 ET).
- [x] Delivery to readers on the prototype: a reader pulls what changed after its checkpoint; no payload is stored (2026-11-06 11:29 ET).
- [x] Operator's decision: stop writing the `journal`, `export` and `graph` payloads, given that none is read. Operator, 2026-11-06 11:36 ET, to "May I stop writing the three delivery payloads?": "1 yes".
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
