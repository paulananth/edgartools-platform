# 176: The three blocked sources are wired into Bookkeeping before any is switched on

Priority: 176. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 19:13 ET (operator, 2026-11-02: "wire bookkeeping then only we can turn on").

Type: task. Status: resolved (2026-11-02 21:10 ET; operator: "close if it is already done"). Every part is ticked; the sec.registration target moved to ticket 149. Open design notes, not parts: iapd.adv dating by month, and whether the sequence names both iapd.adv targets. Related: [172](172-the-thirteenf-securities-run-through-bookkeeping-and-the-change-journal.md) (the 13F target is the pattern), [174](174-sec-prospectus-final-prospectuses-looked-up-on-mdm-then-landed-in-silver.md) (`sec.prospectus`).

## Question

Nine sources have a Bookkeeping target in `rules/source-sequence.yaml`. Three have none and are blocked with `source_target_not_configured`: `sec.ownership`, `iapd.adv` and `sec.registration`. The operator turns sources on one at a time in the new local store (`source-by-source`), and wants every target wired first. No source is registered, approved or switched on by this ticket.

## What is known (no request)

- `sec.ownership` has its read rules (XML and SGML), its quality file and two silver specs (`insider_ownership`, `insider_position`). It needs a mastering target for the owner (a Person or a Company) and `silver.land` steps for both silver tables, after the merge, so each row finds its MDM ids.
- `iapd.adv` has its read rules (two CSV files and a combine contract) and its quality file. It needs a mastering target.
- `sec.registration` has a capture-only target (version 1) and no read rules. What its second step reads is the operator's decision (ticket 149 kept the document unread first), so it is last.

## Change Journal (operator, 2026-11-02: "also needs change journal")

Every target that processes files ends with the `journal.record` step (the 13F target's `processed`), so the Change Journal skips a file already processed with the same source, key, content hash and processing identity, and names every file again when a rule changes. Each source below is done only when a test shows both: a second pass changes nothing, and a changed rule names every file again. A capture target ends at capture and has no such step (`sec.company`'s, GLEIF's and OpenFIGI's have none), so `sec.registration` gets one with the target that reads its documents.

## Order (recommended)

1. `sec.ownership`: its rules and silver are complete.
2. `iapd.adv`: its rules are complete; no silver.
3. `sec.registration`: nothing to wire before its documents are read (ticket 149).

## Parts

- [x] `sec.ownership`: the mastering target (read, prepare, merge, landings, processed): `bookkeeping` v2 in `rules/sources/sec.ownership/source.yaml`, with an `owner_record` table in both read contracts holding each owner as one object; plan test `tests/mdm/test_ownership_target.py` (2026-11-02 19:37 ET)
- [x] `sec.ownership`: the `silver.land` steps for `insider_ownership` and `insider_position`, after the merge: five landings that require the read step and the merge; real workers on Postgres (`tests/integration/test_ownership_target_postgres.py`) land 2 owners and 4 lines, and fail when the landings require only the read step (2026-11-02 19:37 ET)
- [x] `sec.ownership`: the Change Journal step ends the target; tests at plan level (a second pass changes nothing; a changed rule names every file again, `tests/mdm/test_ownership_target.py`) (2026-11-02 19:37 ET) and through the real workers on Postgres (a second pass changes nothing; a changed rule names every file again)
- [x] `sec.ownership`: `target: mastering` in `rules/source-sequence.yaml` (after `sec.nport.fund`), pinned-order tests and the Mapping Document updated (2026-11-02 19:37 ET)
- [x] The engine lets a silver landing wait for a merge ([#1316]: plan tests; failed before on `a landing follows one read step`) (2026-11-02 19:37 ET)
- [x] `iapd.adv`: two targets, one publication each (a target prepares one): `mastering` (read the filings and the custody rows, combine, record, prepare, merge, processed) and `custodians` (read, combine, record, prepare with `distinct_on`, merge, processed) (2026-11-02 19:49 ET)
- [x] `iapd.adv`: the Change Journal step ends both targets; plan tests (`tests/mdm/test_iapd_adv_targets.py`: a second pass changes nothing; a changed rule names every file again; recording the filings does not skip the custodians of the same file) (2026-11-02 19:49 ET)
- [x] `iapd.adv`: the preparation may name `distinct_on` (validators for step keys and unit keys, and the planner; `tests/mdm/test_prepare_distinct_on.py` failed before on `A step's keys are nonempty text`) (2026-11-02 19:50 ET)
- [x] `iapd.adv`: real workers on Postgres (`tests/integration/test_iapd_adv_targets_postgres.py`: the filing carries its 3 custodians; 4 custody rows make 3 custodian records, 4 without `distinct_on`); `rules/source-sequence.yaml` and the pinned-order tests (2026-11-02 19:50 ET)
- [x] `sec.registration`: the operator decides what the second step reads: "Capture and Change Journal only (Recommended)" (operator, 2026-11-02 19:56 ET); its documents are not captured (the run was left at 2 of 9,538 verified, about 32 hours) and nothing reads them yet (the HTML reader and the profile are open in 149), so no target beyond capture is wired
- [ ] ~~`sec.registration`: its target beyond capture, with the Change Journal step, tests and `rules/source-sequence.yaml`~~ deferred to 149: the target that reads the documents (IPO pipeline, offering terms) needs the captured documents, the HTML reader and the profile; its last step is the Change Journal step, and the source joins the order then. Its capture target already follows the pattern (it ends at capture, as `sec.company`'s does)
- [x] Learning → skill: `skills/change-journal/SPEC.md`: a capture target ends at capture and has no `journal.record` step; the step ends the target that processes the files (2026-11-02 19:56 ET)

## Findings while building `sec.ownership`

- The read step takes the SEC submission files (`*.txt`); the source has no acquisition feed yet, so which captured files carry that name is to be confirmed with the capture of the ownership files (needs the operator's permission for the SEC requests).
- A step after a merge cannot land a read unit's rows without the engine change above: `silver.land` took exactly one predecessor, and the merge's units carry no read unit.
- The installed-bundle test installs the committed `HEAD`, so it must run after the commit; it takes about 7 minutes locally.

## Findings while building `iapd.adv`

- A target prepares one publication, so the filings and the custodians are two targets (as GLEIF's pair file is). The source sequence runs `mastering` (the filings); the `custodians` target is run by hand, first, so the CUSTODIAN links of the filings find their targets. Whether the sequence should name both is open.
- The run fact `published` (the month end as an ISO instant) is required by both targets.
- The ruled dating by month (`effective_at` per file, operator 2026-10-22) is not built: the planner always gives the preparation a publication key and revision, and the worker then refuses `effective_column`. `effective_at` would be a run fact. Open: its own decision.
- The step validator, the unit validator and the planner each assumed every key is text; `distinct_on` is the first list. Both validators now share one helper.
- The captured files are the monthly zips (`*.zip`) under `reference/iapd_adv_bulk/<month>/`; the capture of them needs the operator's permission.

## Not in this ticket

Registering, testing, approving and switching on a source in the new store: each waits for the operator's words, one source at a time.
