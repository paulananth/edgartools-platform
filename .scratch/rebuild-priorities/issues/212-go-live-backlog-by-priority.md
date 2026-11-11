# 212: Go-live backlog by priority

Priority: 212. Map: [Rebuild priorities](../map.md). Opened 2026-11-11 15:02 ET (operator: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").

Type: task, charted with wayfinder. Status: open. Blocked by: none.

## Destination

Every part still open in the Rebuild priorities map, in one list, ordered by what the go-live needs. Each ticket it came from is closed with the part struck through and `deferred to 212`; the part's full text stays in that ticket. Tickets 20 and 181 are claimed by Codex and are not listed or edited here.

## Checklist, by priority

### 1. The go-live path (do these first, in this order)

**[211](../issues/211-finish-the-go-live-the-remaining-sources-and-the-hosted-store.md) 211: Finish the go-live: the remaining sources and the hosted store** (open)
- [x] (2026-11-11 16:45 ET) [211] Hosted SEC company load: 76,380 documents in 150 bundles, 2 at a time, the target marked local (read and combine on the Mac, database writes only for records, merge and processed), finished 16:43 ET after about 3 hours with two stops. First pass 13:32 to 15:55 ET: 128 bundles, about a minute a bundle, then 22 bundles failed at `mastering.merge`. Cause (traceback, then fixed in PR 1677 with a test that fails on the old code): a bundle whose every document is set aside (not a listed operating company) has no records and so no kind, and `merge_file` raised `KeyError('')` looking up the empty kind in the release step; the `local-staging` load of 11-10 predates that step. After the fix the rerun finished the leftover runs (44 runs, 0.8 to 1.3 min each) and reported "0 documents loaded, 76380 already loaded before". The store holds 5,091 company records (the listed operating filers), the same count as `local-staging`.
- [ ] GLEIF Level 1 (finds Companies, never creates), then GLEIF relationships
- [ ] OpenFIGI, then 13F securities and N-PORT security (Securities)
- [ ] SEC ownership (Form 4 relationships)
- [ ] 13F filings
- [ ] SEC company facts and SEC registration (Silver only)
- [ ] Reconcile waiting links once both endpoints exist; record the totals
- [ ] Skill gaps from the rules step: `data-operations` step 2 says "`rules load` saves every file under a root; do not use it here" and step 3 omits `governance.env`, while the go-live path for a new store is `rules load` then `rules activate` with `governance.e...
- [ ] Ticket 199's open parts that a fresh load meets: the rules version recorded on mastering records, and the Silver `links` stale-lease stop seen in the GLEIF loads.
- [ ] Ticket 02's origin check of the 327 governed-store runs done first, since an empty start erases that evidence.
- [ ] Whether a source that cannot yet load (ticket 79 N-PORT run builder, ticket 80 OpenFIGI listing enrichment, ADV and 13F mastering targets) is deferred or loaded as far as its path supports. The load sequence says to report the missing source and stage, not...
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
- [ ] Load each source into the hosted store from the local captures, no AWS (2026-11-11 06:02 ET; operator: "after init load each source in snowflake from local no aws"). Done so far on the hosted store: GLEIF subfund pairs (1 document), N-PORT registrants (1),...
- [ ] Hosted counts, first part done (2026-11-11 16:45 ET): ticket 209's count on the hosted store after the SEC company load (read-only, 102 s): 446,704 records with a golden record, 393,459 explained as creators, 53,245 by an identifier, 0 by a decision (the waterfall pass has not run there yet), **0 unexplained**, none for any source; 415,730 golden records. Still to record: each source's stored and set-aside counts, and the count again after the remaining sources load.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".

**[210](../issues/210-only-mastering-and-silver-touch-the-database.md) 210: Only mastering and silver touch the database** (open)
- [ ] First, smaller and for every step: a long-lived `bookkeeping serve` child (one JSON command a line, one engine, a memo of the run's immutable parts) and one `Session` per thread in `control.py`; the renewal thread gets its own. Measured today: about 2 s a c...
- [ ] Then measure the combine claim in a warm process (163 s measured; one store query a step did not move it).
- [ ] Design (operator rulings: no run is planned before the local steps; "drop step 6"): seven steps. Captured files; ask the journal (new or changed?); Source Extract and Combine extracts run locally through the worker modules and write files with receipts, wit...
- [ ] Build it, with a test that fails before the change (a read and combine of N units issue no database call).
- [ ] Prove on `local-staging`: a small load gives the same counts as before.
- [ ] Hosted OpenFIGI answers load finishes inside the operator's 1 to 2 hour window.
- [ ] The marker on the sources' `mastering` targets (`local: true`), with new rule versions and approvals, and the hosted activation. In progress: OpenFIGI marked in `rules/sources/openfigi/source.yaml` (config check: the staged run holds prepare, merge, process...
- [ ] Generated work (`generated_step`) is refused locally; check which sources use it before they are wired.
- [ ] The engine's own slot filling still copies `compose_document` until PR 1653 lands (GoF finding 1).
- [ ] A committed proof that local outputs hash the same as the database path's, and that read and combine make no database call: the 10-document run was an ad-hoc run (17 of 17 hashes equal); a test needs a small real source, so it is part of the second-source p...
- [ ] A rerun after a failure re-executes every local unit; skip units whose receipts already exist if the full-size run shows it costs.

**[202](../issues/202-name-count-inside-the-gleif-merge.md) 202: Name Matching inside the GLEIF merge** (open, taken up again (2026-11-11 07:05 ET; operator: "Name C)
- [ ] Name, former name and place as separate approved rules, each with its own proof (moved from ticket 206, step 3, 2026-11-10 06:43 ET). Built inside the merge with parts 1 to 3 of the build plan; each rule is approved on its own measured evidence.
- [ ] Measure the SEC-side count from the stored SEC Company records against the file's count on the same data, and show they agree (counts only).
- [ ] Take the `name_count` step, the run file and the `--file name_count` input out of `sec.company`.
- [ ] Move the count into the GLEIF merge, with a test: a name unique on both sides binds, a name shared on either side waits, and a scoped load counts the whole file.
- [ ] Drop `edgar-warehouse mdm name-count` as a separate command once nothing uses it, and update `CONTEXT.md` ("Name Matching") and the load sequence's step 4.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
- [ ] Replay check, counts only: for every GLEIF record now attached to a Company, and every unattached one, the search's answer (same Company, another Company, several, none) against the cascade's; the differences go to the operator.
- [ ] Build the search inside the GLEIF merge: name plus place, former name plus place, exactly one mastered Company; several go to review; the earlier binding stays when a later load makes the name shared.
- [ ] New proof of the new rules (Wilson bound, adversarial cases, a cohort) and the approval line.
- [ ] Remove the `name_count` step, the run file, `mdm name-count`, `name_count_file.py` and the cascade code once nothing uses them; update `CONTEXT.md` ("Name Matching") and the load sequence.
- [ ] Delete the job: `mdm name-count`, `name_count.py`, `name_count_file.py`, the `name_count` step and run file of `sec.company`, `--file name_count`, the `name_count` role of `mastering_name_key`, and what reads them (`name_census_match@1` and the readers in `...
- [ ] Rename the rule words that say cascade or count: the primitives and rules take the waterfall matching words; new rule versions; the approval line, Mapping Documents and pins that follow.
- [ ] Update the skills, docs and the load sequence (step 4) so none names the job; a SEC company load no longer waits for a file.
- [ ] Keep both words out: an architecture test fails on `name count`, `name_count`, `name-count` or `cascade` in tracked code, rules, skills and docs (the tickets under `.scratch/` are history and stay).
- [ ] Remove "cascade" as a term and use waterfall (operator, 2026-11-10 12:12 ET: "Remove Cascade as a term and use waterfall"): `CONTEXT.md` has no "Cascade" now; the code, rule, test, skill and doc words (`cascade.py`, `cascade_pass@1`, 139 uses in 13 files of...
- [ ] Step A, build the waterfall pass: `waterfall.py` computes the pairs from the SEC Companies in the store and the GLEIF publication (the whole publication, once), and writes its answer as the name keys the merge already reads. Proof: on the same data it gives...
- [ ] Step B, the GLEIF merge reads the waterfall pass instead of the file the SEC records carried; the rule steps and primitives take the waterfall names; new rule versions, the approval line, Mapping Documents and pins.
- [ ] Step C, delete: the `name_count` step and run file of `sec.company` (a SEC load no longer waits for a file), the `name-count-*` pipelines, `mdm name-count`, `name_count.py`, `name_count_file.py`, `cascade.py` (its passes live in `waterfall.py`), the Rust pa...
- [ ] The counts-only comparison on real data against the answer the records carry (`provenance.matching.name_count`), through `differences`: same, other LEI, only new, only stored. `local-staging` holds 5,091 SEC company records, so a full proof needs the full c...
- [ ] Read the stored answer for the comparison through the profile's cascade fields (`matching.py:56-60`): `differences` expects `{cik: {"lei": ...}}`, and a record holds its entry at `provenance.matching.name_count.<cascade_field>` with the LEI at `<cascade_ide...
- [ ] The GLEIF reader must build each entity's keys (legal name plus other names a filer wants) and its address count over every supported GENERAL entity, as `name_count.fold_reading` does, and say where the passes and `over_shared` come from (the Company rules'...
- [ ] Steps B and C as written above; `differences` is deleted with the old file in step C.
- [ ] Step A, part 1: write the `wanted` lookup the reading takes from the filers' names (`wanted_names`), and port the reading's own check that the lookup it was given equals the population (`name_count_file._gleif`).
- [ ] Step A, part 4: store the pairs under the publication's identity and let the merge read them (see the parts above).
- [ ] Still to delete or rename: `NAME_COUNT_VERSION` and the `name_count` role of `mastering_name_key`, the `name_census_match@1` primitive and the rules that read a record's name-count entry, the `name_count` input field of the company dataset contract (a new c...
- [ ] Still open: the `name_count` role of `mastering_name_key` and the `name_count` route (`candidate_paths`), the `name_count_*` fields of the comparison profile, the primitives `jurisdiction_agrees@1`, `jurisdictions_do_not_conflict@1` and `postal_agrees@1` (n...
- [ ] Still open: the container name `name_count` in a record's provenance and the company dataset contract (`name_count_field`; a new contract version, digest tests re-baselined), the three place primitives no live rule calls (`jurisdiction_agrees@1`, `jurisdict...
- [ ] Still open: the container name `name_count` in a record's provenance and the company dataset contract (a new contract version, digest tests re-baselined), the `cascade` to waterfall words, the word-ban architecture test, the `waterfall` target and chaining...

**[204](../issues/204-step-1-every-source-record-goes-through-mastering.md) 204: Step 1: every source record goes through mastering** (open)
- [ ] Prove a name binds only on exactly one golden record (moved here from ticket 206, 2026-11-09 17:42 ET; operator: step 1): for each name rule, a name that one golden record holds joins it; a name that two golden records hold goes to review and joins neither;...

### 2. Mastering correctness the go-live depends on

**[203](../issues/203-company-matching-identifiers-first-name-last.md) 203: Company matching, identifiers first and name last** (open)
- [x] (2026-11-11 16:08 ET) [203] Registrant LEIs against the whole GLEIF Golden Copy (read-only, counts only, 62 s, local-staging registrants against the 2026-09-11 file): 1,947 registrants, 1,938 with a LEI, 1,934 distinct LEIs; **all 1,934 equal a GLEIF LEI** (0 not found). Of the 9 registrants with no LEI, 6 have a name equal (case, punctuation and spacing folded) to a GLEIF legal name. Place not measured.
- [x] (2026-11-11 16:08 ET) [203] The registrant LEI rule `nport-registrant-lei` is declared, switched on by the operator ("Master it ;consider it a source") and proved by its limited test in both source orders and a second pass (ticket 203's own parts).
- [ ] State "no other identifier available" as one precondition shared by every name rule (it exists today as `holds_no_other_lei@1` for LEI only), and add former name to the name rule family with its own proof.
- [x] (2026-11-11 16:08 ET) [203] Decided 2026-11-10 13:23 ET with no change (operator, "Yes, no change (Recommended)"): the adviser's LEI and the fund series LEI stay lookups.
- [ ] Learning → skill: name the skill line this ticket changed, or write "none".

**[200](../issues/200-openfigi-name-finds-a-company-and-waits.md) 200: May an OpenFIGI name find a Company and wait?** (open)
- [x] (2026-11-11 16:08 ET) [200] Decision (operator, 2026-11-11, asked one question with the evidence): "Leave OpenFIGI out (Recommended)". An OpenFIGI answer joins a Security by its identifiers only and never looks for a Company by name; the current rule stands.
- [x] (2026-11-11 16:08 ET) [200] Not needed: the operator chose to leave OpenFIGI out, so there is no match rate to measure.
- [x] (2026-11-11 16:08 ET) [200] Not needed (same decision): no find-and-wait rule is written.
- [x] (2026-11-11 16:08 ET) [200] Learning → skill: none (a decision to keep the current rule).

**[199](../issues/199-rebuild-mastering-on-three-operations.md) 199: Rebuild mastering on three operations** (open)
- [ ] Stage 4, then: 13F, ownership and ADV from the existing files; the Apple chain from adviser to holding to AAPL.
- [ ] Bookkeeping per file, not per batch; the `processed` step; what the step around the silver writer costs.
- [ ] Measure a real `processed` step again on the next load: the median was 11.4 s over 511 files.
- [ ] OpenFIGI at full size on the final version: 733,538 OpenFIGI records are stored on the local PostgreSQL store, but the mastering tables do not record which rules version loaded them, so "final version" is not proven.
- [ ] Decide whether a waiting `ISSUED_BY` issuer may become a Company. The only route today is a Company rule that lets an N-PORT or GLEIF issuer LEI create one, against the ruling that GLEIF never creates a Company (operator, 2026-10-16: "Wait, config only"). I...
- [ ] The `links` step's "Stale lease" stop in `silver.derive` on a long run: find the lease that expires (the step runs 825 s) and fix it. Narrowed 2026-11-09 (see the PR): the worker heartbeat renews every 30 s on a 120 s lease; the printed error is a database...
- [ ] Parts from ticket 197: sorted 2026-11-08 22:49 ET against what `main` now holds.
- [ ] The catalog read in every bundle (27% of `sec.company` run time): re-measured in part (2026-11-09 09:54 ET). The `catalog` step still exists in `sec.company/source.yaml` and reads the 521 KB ticker file in every bundle of 511 files. The read itself takes 0....
- [ ] Two deadlocks in claims at 3 bundles at once: Bookkeeping's claim path is unchanged; not re-measured. RE-MEASURED (2026-11-10 05:12 ET): on the go-live SEC person load (149 bundles, `local-staging`), 2 bundles at once left 7 bundles stopped (`DeadlockDetect...

**[153](../issues/153-reload-the-security-loads-on-current-code.md) 153: Reload the Security loads on current code** (open)
- [x] (2026-11-11 16:08 ET) [153] Not needed as a separate reload: the go-live loaded OpenFIGI on current code from empty (`local-staging`: 771,554 `openfigi.security.v4` records and 335 `v3`; the hosted store holds 335 so far).
- [x] (2026-11-11 16:08 ET) [153] Done by the go-live: 420,690 N-PORT security records stored of the archive's 420,691 (1 set aside), on `local-staging` and on the hosted store.
- [ ] [153] Counts (`local-staging`, read-only, 2026-11-11): 395,838 Security, 22,766 Company, 12,937 Fund Structure and 31,097 Person golden records; 1,271,374 source records, 0 unexplained. **Not true that no identifier sits on two masters:** 13 SEDOLs and 1 LOANX are each held by two Security masters (14 pairs), 364 tickers by two to four Securities, 231 LEIs by both a Company and a Fund Structure, and 1 CIK by both a Company and a Person. To decide: whether each of the 14 Security pairs is one security (merge) or two (the identifier is wrong on one), whether a ticker may sit on several Securities (it is a lookup, not a join key), and whether one LEI may name a Company and a Fund Structure.
- [ ] "Destination authority expired before save": measure one bundle that has never been merged, per batch (moved from 150)
- [ ] Learning → skill

### 3. Everything else that is still open (by ticket number; a part waits on its own condition)

**[71](../issues/71-mastering-to-done-24-worker-runtime-on-aws.md) 24: The configured worker runtime on AWS (Step Functions and task definitions)** (open, waits for the operator's AWS destinations)
- [ ] The operator names the AWS destinations, stores and roles (Codex's go-live review, items 2 and 4): where consumers are delivered, which PostgreSQL hosts each store, the worker and verifier logins
- [ ] Design: one state machine shape for any target (submit, per step: work and verify until verified, finalize), its timeouts and retries; GoF consult
- [ ] Task definitions for the worker and verifier images; the image build (needs a container runtime)
- [ ] install.sh deploy stages for them; tests; review; PR; deploy only on the operator's word
- [ ] Source activation of SEC Company and GLEIF for live acquisition (the local switch-on over captured files is done: SEC Company by ticket 114; from ticket 02; operator, 2026-10-14: "Move to ticket 71 (Recommended)"): an acquisition proof from a real acquisiti...
- [ ] Source activation of `sec.submissions.person` (from ticket 11): the same acquisition proof
- [ ] `rules run --target mdm` end to end (from ticket 02)
- [ ] The live SEC Company qualification (from ticket 03, L8; parked by the operator until AWS: `.planning/workstreams/sec-company-live-qualification-20261013/TICKET.md`)
- [ ] The run report's row-count change from the last run (from ticket 10, part 2): compare each Bookkeeping run of a target with the last complete run of the same pipeline and target; the per-run counts are each MDM run's `checks` in `mdm.run.report`; a Bookkeep...
- [ ] GLEIF Level 1's records step passes `record_extras: [nport_issuer]` to `mdm.prepare` and fills the reading's `nport_issuers` reference from the N-PORT issuer reduction (tickets 22 and 97; noted 2026-10-16 13:16 ET)

**[170](../issues/170-how-many-workers-and-the-worker-architecture.md) 170: How many workers, and the worker architecture** (parked)
- [ ] Measure: what limits a load today (reader count, Postgres connections, the Merge Stage, memory); one measured run per limit, not a sweep
- [ ] Decide the default worker counts per operation (`source.read`, `mdm.prepare`, `mdm.merge`, `silver.land`) and whether they are rules, flags or sizing from the measured time
- [ ] Decide where each kind runs (local processes, containers, the hosted target) and how leases and logins scale with the count
- [ ] Write the architecture in one page and the numbers in the `data-operations` skill
- [ ] Learning → skill: `data-operations` and `bookkeeping` name the worker counts and the sizing rule

**[174](../issues/174-sec-prospectus-final-prospectuses-looked-up-on-mdm-then-landed-in-silver.md) 174: sec.prospectus: the final prospectuses (424B1 to 424B5), looked up on MDM, then landed in silver** (open, not started)
- [ ] The operator's permission for the SEC requests of this feed, with the forms and the scope (nothing is requested before it)
- [ ] Count the 424B1, 424B2 and 424B5 filings from the captured submissions (no request), and the size of their main documents
- [ ] Decide with the operator which forms and which facts: the offer terms (price, shares, underwriters, exchange), or the document kept unread first, as for `sec.registration`
- [ ] Outside standards first (the research skill): how a 424B prospectus is structured and which parts are tagged
- [ ] Capture: a source `sec.prospectus` with its `acquisition` feed, a Bookkeeping capture target and the Change Journal, shaped like `sec.registration`
- [ ] The look-up: each filing's filer found in MDM by CIK; a filer MDM does not hold is set aside with its reason, never created here
- [ ] The silver table (the Silver Spec, its grain and key, the link to the Company), landed through the `silver.land` step, with its first quality checks (the operator decides the checks)
- [ ] A limited proof only: a few invented documents, a second pass that changes nothing, an unchanged file skipped
- [ ] The Mapping Document and the Data Catalog entry are regenerated; tests that pin the source order are run before the first push
- [ ] Stores and containers a test run leaves are removed
- [ ] Learning → skill: the `data-onboarding` and `company-financials` skills name this feed and its look-up, or "none"

### 4. Check, then drop (the ticket's status says done, closed or resolved; the box is left over)

**[32](../issues/32-profiling-08-recreation-proof.md) 08 Recreation proof** (resolved (2026-11-01 15:33 ET, accepted))
- [ ] Real company names quoted in older tickets on `main` reach `rulings.jsonl` (the operator's own words among them, kept as written): not fixed here

**[68](../issues/68-clean-mdm-07-qualify-and-cut-over.md) Qualify Snowflake Postgres and rehearse cutover** (open, later: the hosted Snowflake Postgres cut-over is under)
- [ ] Run `mdm migrate` on the hosted store once it exists: it carries every migration the local store has, including 005–007 (ticket 18) and 010 (ticket 19), moved here 2026-10-18 12:25 ET
- [ ] Learning → skill

- [ ] Learning → skill: name the skill line this ticket changed, or write "none".
