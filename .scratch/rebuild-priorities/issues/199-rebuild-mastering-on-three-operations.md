# 199: Rebuild mastering on three operations

Priority: 199. Map: [Rebuild priorities](../map.md). Opened 2026-11-06 10:18 ET (operator: "yes open the rebuild ticket and start"). Follows ticket 197, which holds the prototype's results.

Type: task. Status: closed (2026-11-11 15:02 ET, operator: "Close all tickets"): its open parts are ticket 212's. Blocked by: none.

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
- [x] Point the Rules Database at `mastering.merge`: done with stage 4 unit B, the rule version is active on all 13 sources and merge/platform (PR 1481, 2026-11-06 23:30 ET); every merge step in `rules/sources` is `mastering.merge`.
- [x] Stage 3: `mdm rebuild`, every record replayed and compared: 431,028 masters match, and 4,797 of 4,797 for the records the old load stored late (2026-11-06 15:43 ET).
- [x] Review of stages 1 to 3 on Standards, Spec and GoF: two integer columns made BIGINT, a merge writes identifiers once, `compare` holds no transaction, `master_ids` deleted, the lock tested with two writers. The lock is one row for all kinds, not one a kind, since the changed-file number readers pull by runs across kinds; the prototype lines here describe one a kind. Without the lock the new test gives 400 masters for 200 (2026-11-06 15:47 ET).
- [x] Stage 4: readers moved; relationships with the silver write. Readers pull by checkpoint, `consumer.py` and `inspection.py` are deleted, links are the `relationship` silver table from `silver.derive` (PRs 1478, 1481, 1487, 1520; checked 2026-11-08 21:09 ET).
- [x] Stage 4, facts rule: `facts.yaml` has its `execution` block, and a test passes every `source.read` contract through the worker's own check, PR 1475 (2026-11-06 18:30 ET).
- [x] Stage 4, retro checks: the guard runs `rules approvals check` when rules change, PR 1476; three skill rules, PR 1477 (2026-11-06 18:37 ET).
- [x] Stage 4, `context` on the mastering tables, PR 1478: 12 Apple questions, 7 the same as the old answers, 5 better, 0 worse (2026-11-06 20:07 ET).
- [x] Operator's ruling: name fragments are not stored. "use 7 wastes", to dropping them: 82% of lookup rows on the page measured; a search with no whole word scans the masters. The build fell from a projected 100 minutes to 6 on the local store, PR 1478 (2026-11-06 20:07 ET).
- [x] Operator's ruling: tests of code nothing calls are retired, not moved. "decommision un used tests use 7 wastes": the old search and detail scenarios, PR 1478 lists each claim and where it went (2026-11-06 20:07 ET).
- [x] OpenFIGI creates no Security only when a filing names it, configurable: measured 2026-11-09 05:48 ET on the local store, 164 of 461,455 masters hold OpenFIGI records alone (0.04%); 733,538 OpenFIGI records sit on 382,649 masters, the rest joined to N-PORT's. The setting exists: `on_no_match: wait` on `openfigi-security-cusip`, `-isin` and `-figi` in `rules/merge/kinds/security.yaml`, as N-PORT's FIGI rule already does. Operator, 2026-11-09, asked whether to switch it on (a new approved rules version, rule tests, a replay of 733,538 records for 164 masters): "Leave it on create (Recommended)". It stays `mint`; reopen if the count grows. Earlier note: Measured 2026-11-06: of 393,674 Securities, only 164 come from OpenFIGI alone, so the setting removes few; N-PORT names the rest. Operator's ruling: a security is mastered only when a filing names it, and that is configurable. "agree with you recomendation but make it configurable". OpenFIGI adds to a master and creates none; 80% of security masters today are mortgage and municipal lines from it. Measure the count first; replay OpenFIGI under the rule.
- [x] Stage 4, unit A: `MdmIds` and `from_company` on the mastering tables; Apple's financial rows on its new master. Done 2026-11-06 23:30 ET: PR 1481; Apple's 25,135 facts, 437 line items and 760 measures sit on its new master, 0 on the old id.
- [x] Stage 4, unit B: every source's merge step on `mastering.merge`, CIK v2 in the same rule version, links with the silver step, `required_consumers` gone. No load runs before this version is active. Done 2026-11-06 23:30 ET: PR 1481; `rules test` passes, and the rule version is active on all 13 sources and merge/platform.
- [x] Stage 4, unit C: the remaining N-PORT Security batches on the new path, then links; Apple's first `ISSUED_BY`. Done 2026-11-06 23:30 ET: 421 batches merged in 18 min and verified; 55,320 links built (42,383 `ISSUED_BY`, 12,937 `IS_SUBFUND_OF`) in 7 min; AAPL has its `ISSUED_BY` to Apple, and 57 securities name Apple as issuer.
- [x] Rule tests on the new merge. Done 2026-11-06 23:30 ET: PRs 1485 and 1486. 13 test files moved; 2 stay on the bridge because they test the old engine, and leave in stage 5. Moving them found two gaps, fixed in 1485: only identifiers a rule minted could be found (153,031 tickers, SEDOLs and LoanX ids added to the local store), and the exact-name rule never ran.
- [x] Links at full size. Done 2026-11-06 23:30 ET: PR 1487. `add_review` was quadratic; the build ran 30 min unfinished, and takes 7 min with a set.
- [x] N-PORT holdings in silver: 0 of 5,347,869 rows. All four figures reach 12 decimals against `DECIMAL(38,10)`. Waits on the operator: "10 is fine" means cut, round, or keep 12.
  - [x] The scale: DECIMAL(38,12), as filed (operator, 2026-11-08: "Scale 12, as filed"); 3,863,454 of 5,347,869 percentages carry more than 10 places. PR 1505, merged 2026-11-08 17:12 ET.
  - [x] Landed: 5,347,869 of 5,347,869 rows, 3,960,885 with a Security, 4,516,886 with a fund, all with a registrant; verified by the land's own check and by count, 2026-11-08 18:15 ET. The first land stopped at 3,792,909 rows at 17:26 ET: the Docker VM (3.9 GiB, shared with the OpenMetadata stack) ran out of memory and Postgres killed a backend. The rerun took 17.2 min; it writes by key, so the rows already landed were matched, not doubled.
- [x] 198,808 reported links have no other end yet (`unresolved_endpoint`): measure why before stage 5.
  - [x] Measured 2026-11-08 17:10 ET: 199,597 are N-PORT ISSUED_BY, 1,239 others; 20,255 distinct issuers missing, two of them 45,851 and 19,746 links. Who those two are: not yet looked up.
  - [x] Why, 2026-11-08 17:36 ET: N-PORT names an issuer by LEI and the link waits for GLEIF's record of it. The local store holds 3,716 GLEIF records, a sample load of 2026-11-06; the golden copy on disk holds the full file. The top two missing issuers are Fannie Mae (45,851 links; its LEI hashes to the missing subject, and the golden copy has it) and Ginnie Mae (19,746). Not a defect: the links resolve when GLEIF loads in full.
- [x] Steward split and revoke: the new store holds split, override and revoke decisions, and `mdm steward split` runs on `mastering.merge` through one transaction (`merge.split_merge`), PR 1518 (merged 2026-11-08 20:23 ET).
- [ ] ~~Close the stale runs `bfe91575` and `61f32231`~~ deferred to none: Bookkeeping has no close or abandon command, and a run ends only when every unit verifies. 30 runs sit in `running` on the local store (the holdings land finished outside them, 2026-11-08 18:15 ET). Nothing reads them; a command for them would be built for no reader.
- [ ] ~~Stage 4, then: 13F, ownership and ADV from the existing files; the Apple chain from adviser to holding to AAPL.~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
  - [x] ADV June 2026: custodians mastered (494 records, 231 bound: 114 by LEI, 106 by broker-dealer number, 11 by exact name; 263 wait); `adv_custody` 3,022 rows, 3,022 with an adviser id and 2,541 with a custodian id. Verified by count, 2026-11-08 13:05 ET.
  - [x] 13F from the p07 files: 52 information tables, 10 managers; 283,725 holdings, 283,715 with a Security; 356 AAPL rows on the one AAPL Security, 355 with a manager (5 managers). Verified by count, 2026-11-08 13:15 ET.
  - [x] Advisers join the SEC Company holding their Item 1.D(3) CIK (operator: "Both"): rule iapd-adv-cik, filings as iapd.adv.filings.v2. PR 1503, merged 2026-11-08 17:04 ET. Real June file: 704 filings carry CIKs; 2,935 of 2,938 keep their master; 3 in review (advisers this store made from the CRD first).
  - [x] The Schedule D 7.A RELATED_PERSON link (operator: "RELATED_PERSON (Recommended)"): PR 1508, merged 2026-11-08 18:28 ET. Built on the March 2026 file: 54 links.
  - [x] The Apple chain from an adviser, verified by query on the local store, 2026-11-08 19:29 ET: HILLTOP SECURITIES ASSET MANAGEMENT, LLC, RELATED_PERSON (from 2026-03-31, observed), Hilltop Holdings Inc., 6 13F rows on AAPL across 4 filings, the one AAPL Security, ISSUED_BY, Apple Inc.
  - [x] Finding on the way, PR 1510 (merged 2026-11-08 19:08 ET): no ADV record carried a time, so every link that states no start of its own (CUSTODIAN, RELATED_PERSON) waited as `unknown_relationship_start`, 17,951 of them; the test passed only because its own prepare keys dated the filings. The filings adapter now states `effective_at: published`, and the test prepares with the keys the source declares (it failed `0 == 2` before). After reloading March: 11,057 CUSTODIAN and 54 RELATED_PERSON links; waiting for a start fell to 4,966. Link rebuild 17.6 min; June reloaded at revision 202606 (2026-11-08 19:29 ET).
- [x] Stage 5: the old path deleted (parts 1 to 3 above, 2026-11-08 20:57 ET).
  - [x] Part 1, PR 1509 (merged 2026-11-08 18:52 ET): the `mdm.merge` and `mdm.publish` workers, the graph-publication pipeline and its approval line, `mdm force-publish`, and `forced_publication`, `journal_delivery`, `payloads`, `publication`: 1,721 lines out, 173 in. `mastering.merge` took its staging step over. CI first failed twice in the installed-bundle test: its policy had no `kinds` entry, then field rules in two places; tested through registration the second time.
  - [x] Part 2, PR 1511 (merged 2026-11-08 19:08 ET): `execute_manifest` and `mdm convert-native`; `execution.py` keeps `batch_input`. The refusals of a member that differs from its manifest are tested on `batch_input` directly.
  - [x] Part 3, PRs 1514 to 1518 and 1520 (merged 2026-11-08 20:57 ET): the old merge, `run.py`, `prepared_runs.py`, `master_reads.py` and the other old modules only they reached are deleted, 1,317 lines out. The tests that used them moved to `mastering` (ADV custodian link, N-PORT links, source priorities) or were retired with the old store's own indexes and views. CI failed once on a bundle test that still named the old merge module.
  - [x] `consumer.py` and `inspection.py` are gone, checked on `origin/main` 2026-11-08 20:57 ET. `mdm/prepared_publication.py` stays: `execution.py` and `store.py` still import it.
- [x] Withheld values on the prototype, by the engine's matching (2026-11-06 11:03 ET).
- [x] Withheld values on real `sec.nport.security` records: 23 ISIN values withheld across 10 chosen batches, and no identifier on two masters; the 5 batches of the old load gave identical masters (2026-11-06 15:43 ET).
- [x] Records set aside by classification on the prototype, 152,557 of 152,557 (2026-11-06 11:03 ET).
- [x] Delivery to readers on the prototype: a reader pulls what changed after its checkpoint; no payload is stored (2026-11-06 11:29 ET).
- [x] Operator's decision: stop writing the `journal`, `export` and `graph` payloads, given that none is read. Operator, 2026-11-06 11:36 ET, to "May I stop writing the three delivery payloads?": "1 yes".
- [x] `consumer.py` and `MdmIds` on the new tables: `MdmIds` on the mastering tables (PR 1481), `consumer.py` deleted (PR 1520). Per-record lookups are the `reads` module and `mastering_lookup*` tables, tested in `tests/storage_adapters/test_mastering.py` (2026-11-08 21:09 ET).
- [x] Database-side safety on the prototype: one lock per kind, a real kill, two writers, a restricted login, on both engines (2026-11-06 11:29 ET).
- [x] Database-side safety in production code, through the storage adapter: `tests/storage_adapters/test_mastering.py` runs on PostgreSQL and MySQL in CI, with a failed file leaving nothing, two writers on the same identifiers leaving one master each, and the runtime login unable to erase a decision or change a table. The old routines are deleted (PR 1520, 2026-11-08 21:09 ET).
- [x] The thin slice: records to reader on both engines in `test_mastering.py` (a reader stays in step by asking what changed; finds a master by source key, identifier and after a merge), and on real files the Apple chain from adviser to AAPL (2026-11-08 21:09 ET).
- [x] Rule which rules allow a merge from the rule itself: the engine's matching does (2026-11-06 11:03 ET).
- [ ] ~~Survivor by `published_at` then id, as replay does~~ deferred to none: measured 2026-11-08 21:16 ET on the local store, 9 merge decisions across about 430,000 masters, 0 aliases. `merge.py` keeps the earliest created master (`store.oldest`) and `rebuild.stored` replays in key order, so they could pick another survivor for those 9 at most. A rule for 9 cases is built for no reader (seven wastes); reopen if merges grow.
- [ ] ~~Bookkeeping per file, not per batch; the `processed` step; what the step around the silver writer costs.~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
  - [x] Measured from the Bookkeeping event times already on the local store, 2026-11-08 21:52 ET (no new run; 14,581 work items, 12,760 events). Time from one verified step to the next in a run, median and count: `processed` 11.4 s (348), `merge` 12.7 s (254), `land` 13.0 s (120), `name_count` 7.2 s (151), `combine` 5.4 s (304), `records` 5.4 s (300), `requests` 1.5 s (8,819), `read` 0.9 s (366). These gaps include waiting for the next claim, so they are an upper bound on each step's own cost. `processed` is `journal.record`, one Change Journal write for a file set: 11.4 s for a row is the step's fixed cost, not its work.
  - [x] The worker's own cost, measured 2026-11-08 22:01 ET on this machine: importing `edgar_warehouse.workers.journal_record` 0.01 s, its journal and changed-files imports 0.19 s, opening the Change Journal 0.14 s, `import edgar_warehouse.cli` 0.02 s. The worker costs about 0.3 s, so most of the 11.4 s median gap is not in it. The Bookkeeping loop has no poll sleep (only the retry back-off in `clean/engine.py`).
  - [x] Control calls measured 2026-11-08 22:10 ET: a Bookkeeping command (`python -m edgar_warehouse.bookkeeping runs`) takes 0.22 to 0.25 s warm, 0.75 s first. A step makes about six, so about 1.5 s. Not the 11 s.
  - [x] The suspect was wrong, 2026-11-08 22:22 ET. `drive` pauses 15 s only when a pass changes no counts, which a normal step does not do; an empty worker pass costs 0.3 s on this machine. The cost is in the work: a `processed` unit records about 511 files (300 units read, median 511, max 512), and `journal.record` appends them one at a time (a stored-routine call, then a read-back, then a receipt check) and `verify` reads each one again. Measured on the local journal: a read 4.7 ms, a verify 3.8 ms, 500 of each: 2.4 s and 1.9 s. With the appends that is the 11.4 s median.
  - [x] Journal a file set in batches, no new routine or migration: `get_many`, `append_many` and `verify_many` on one connection with one readiness check, and `journal.record` uses them (2026-11-08 22:38 ET). 511 events on the local engines, single against batch: PostgreSQL append 4.03 s to 0.27 s, verify 1.84 s to 0.06 s; MySQL append 6.56 s to 1.42 s, verify 1.23 s to 0.08 s. MySQL's routine commits each event itself, so a refused batch keeps the events before it; recording is idempotent and the worker settles the rest singly. Two adapter tests on PostgreSQL, MySQL and SQL Server (13 passed on each); both fail without the change with `AttributeError: 'ChangeJournal' object has no attribute 'append_many'`. Consulted `/gof-refactor-reviewer` first: no batch routine, since the cost was per-call overhead.
  - [x] Measure a real `processed` step again: measured 2026-11-11 18:02 ET on the hosted store. The gap from merge receipt to `processed` receipt is a median 47.0 s over 150 SEC company bundles (23.1 to 76.7 s), but the Change Journal is not the cost: on the hosted journal a read of 400 keys takes 0.77 s and a round trip takes about 0.1 s (about 4 ms locally). So the batch fix holds, and the rest of the gap is waiting for the next claim and the verifier over the network, which belongs to the hosted speed of Bookkeeping, not to this ticket.
- [x] Person and Fund on MySQL: `test_person_and_fund_join_by_their_identifier_and_a_rerun_changes_nothing` runs both kinds under the real rules on PostgreSQL and MySQL with invented records (a CIK or series id gives one master, a rerun changes nothing); it fails when one expected count is changed (2026-11-09 05:57 ET). Not run: Person and Fund real captures on MySQL.
- [ ] ~~OpenFIGI at full size on the final version: 733,538 OpenFIGI records are stored on the local PostgreSQL store, but the mastering tables do not record which rules version loaded them, so "final version" is not proven.~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [x] The rebuilt path on every source, compared with the engine; the old path deleted (2026-11-09 06:08 ET). Compared: stage 3's `mdm rebuild` replayed every stored record of every kind and matched 431,028 masters, and 4,797 of 4,797 for records stored late (2026-11-06 15:43 ET); 13 rule-test files moved (PRs 1485, 1486). Deleted: PRs 1509, 1511, 1520 (2026-11-08). Limit: 13F, ownership, ADV and N-PORT holdings were first loaded on the new path, so no engine answer exists to compare; their proof is the Apple chain and their own tests.
- [x] GLEIF Level 1 loaded in three scopes on the local store, and its effect on the waiting `ISSUED_BY` links measured (2026-11-09 09:40 ET). One scope of 28,424 issuer LEIs is over the reference file's 10,000-row and 1 MiB limits (`source.read` stops with "a reference table has at most 10000 keyed rows"), so it was split into three of up to 9,500 and loaded with revisions 2, 3 and 4. Each load took about 45 minutes, nearly all in `source.read` streaming the 927 MB zip. GLEIF mastering records went from 3,716 to 27,840 (24,591 distinct LEIs). A full scope needs a rules change: the approved scope should be a lookup set, not a reference table. Each load's `silver.derive` stopped at the `links` step with "Stale lease"; the mastering records had landed, and the links were rebuilt by hand with the real `links.calculate` instead (825 s for the whole store). **Result: no new links.** 72,262 edges before and after (42,696 `ISSUED_BY`), 0 inserted; 209,306 still wait on an unresolved endpoint. Only 6,251 of the 27,840 GLEIF records attach to a Company (3,297 Companies); 21,589 wait, because GLEIF finds a Company and never creates one, and no SEC, N-PORT or ADV Company holds those LEIs. So the waiting links are not a missing load: their issuers are not Companies yet.
- [x] Decide whether a waiting `ISSUED_BY` issuer may become a Company. Decided by the rules, checked 2026-11-11 17:44 ET: phase 1 masters only listed operating filers and sets the rest aside as `classification_deferred`; GLEIF never creates a Company (operator, 2026-10-16: "Wait, config only"); the full GLEIF load added no new links. A Company rule that lets an issuer LEI create one would break both rulings, so none is written.
- [ ] ~~The `links` step's "Stale lease" stop in `silver.derive` on a long run: find the lease that expires (the step runs 825 s) and fix it. Narrowed 2026-11-09 (see the PR): the worker heartbeat renews every 30 s on a 120 s lease; the printed error is a database error, so it is not clear whether renewal failed or the work met a stale lease; Silver's writer carries no lease fence. The worker's failure line now says which (`renewal failed N s after its last success` or `renewal ok: N renewals, last N s ago`), tested in `tests/unit/test_worker_renewal.py`. The next failed load names the cause.~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~Parts from ticket 197: sorted 2026-11-08 22:49 ET against what `main` now holds.~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
  - [x] The `processed` step, 11 s for one row per file set: batched journal writes, PR 1528.
  - [x] The 7 to 26 s every step costs whatever its work: measured, a control call is 0.25 s and an empty worker pass 0.3 s, so about 1.5 s a step; the rest was the work (above).
  - [x] ~~Bundles that share keys conflict at the merge~~ gone with the old merge: the new merge takes one lock, and `test_two_writers_on_the_same_identifiers_leave_one_master_each` runs on both engines.
  - [x] ~~A resumed run stepping over retained batches~~ gone: the new merge skips a finished file by its key, and a second run changes nothing (`test_a_replay_masters_every_source_and_a_second_run_changes_nothing`).
  - [x] ~~The batch document stored and compared many times (batch, proposal, three consumers)~~, ~~the other 180 statements~~, ~~the floor~~ and ~~why bundle 11 was loaded again~~: all measured the old merge, deleted in PR 1520; the new merge writes by file.
  - [ ] ~~The catalog read in every bundle (27% of `sec.company` run time): re-measured in part (2026-11-09 09:54 ET). The `catalog` step still exists in `sec.company/source.yaml` and reads the 521 KB ticker file in every bundle of 511 files. The read itself takes 0.25 s through the real chain (three reads: 0.28, 0.25, 0.25 s); with a step's overhead of about 1.5 s, one bundle spends about 1.75 s on it. Whether that is 27% needs a real bundle's total time, which has not been run; the file's size says the work is small and the cost is the step, so reading the catalog once per run would save about 1.75 s a bundle.~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
  - [ ] ~~Two deadlocks in claims at 3 bundles at once: Bookkeeping's claim path is unchanged; not re-measured. RE-MEASURED (2026-11-10 05:12 ET): on the go-live SEC person load (149 bundles, `local-staging`), 2 bundles at once left 7 bundles stopped (`DeadlockDetected` in `source.read` claims, and one `Stale lease` at merge); the same command with 1 bundle at once finished all 7 with no failure. SEC company at 2 at once had no stops. So the defect is a concurrency one between bundles at 2 at once, not a data one; the cause is still open.~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
  - [x] Python preparation builds and hashes the batch document more than once: measured by reading the live path and timing it (2026-11-09 11:42 ET). In `mastering.merge` the batch file is hashed twice, once when the step stages it (`artifacts.verified`) and once when `batch_input` reads it (the second keeps "hash and parse the same bounded bytes" true even if the file changes in place). One SHA-256 of a file at the 16 MiB batch limit takes 7.1 ms, so the repeat costs about 7 ms per largest batch, under 1% of a step's 1.5 s overhead; building and parsing a document that size takes about 55 ms. The repeat is real but not worth removing: deferred to none, because the second hash is the check that the parsed bytes are the verified bytes.
- [x] Learning → skill: `skills/mdm-engineering/SKILL.md`, "Writes and transactions" (a lock call commits first, so an all-or-nothing step is one function) and "Retire redundant tests" (dead code by import graph, not a pin list); a link's start and declared keys are in PR 1513 (2026-11-08 21:10 ET).
