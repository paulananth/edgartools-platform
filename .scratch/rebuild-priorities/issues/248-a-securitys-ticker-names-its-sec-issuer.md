# 248: A Security's ticker names its SEC issuer, through the SEC's own ticker file

Type: task (configuration only; no code change). Status: open. Blocked by: none.
Found by the research on common stocks with no Company (operator, 2026-11-16: "Give me list of common stock with no company I will fix this first"; "Find a fix for all this must be a configuration no code change all must be in company master").

## Ruling

Operator, 2026-11-16: "Accept recommendation". A Security's ticker may name its SEC issuer only through the SEC's own ticker-to-CIK file. The file must name exactly one CIK for the ticker, and that CIK must already be a Company. A ticker from any other source stays lookup only. This narrows the 2026-10-14 ruling ("ticker is lookup only") for this one link.

## Rulings (operator, 2026-11-16)

- "Accept recommendation": the ticker rule above.
- On the cost, "yes": the hosted run may load OpenFIGI's 771,554 records again, because this changes OpenFIGI's rules. The load itself still starts only when the operator says to run it; the word covers the cost, not the timing.
- "Fix A yes": a GLEIF record that an N-PORT holding names as its issuer creates its Company (ticket 249). It reverses the 2026-10-16 "Issuer joins, never creates" rule.

## Evidence (hosted store, counts only)

- 18,376 common stock Securities have no Company link: 10,177 state an issuer LEI whose GLEIF record waits unbound (ticket 22's "join, never create" rule); 8,199 state none.
- Of the 8,199: the SEC ticker file finds exactly one existing Company for 1,490 (1,119 US, 371 foreign SEC filers), a CIK with no Company for 87, and nothing for 6,622.
- Against links we already hold: 1,839 of 1,843 Securities whose issuer is an SEC filer and whose ticker the file knows agree (99.8%); 4 disagree. No ticker names two CIKs in the file (10,391 tickers).
- GLEIF's ISIN-to-LEI file (captured 2026-11-16) names an issuer for 169 of the 8,062 ISINs: too few to build on.

## Design (revised 2026-11-16, configuration only)

The first design, a pair-set target in `sec.company` that OpenFIGI reads as another run, does not hold: a target at `grain: run` reads only its own run (`BY_THE_UNIT` in `tests/unit/test_one_shape.py`; bookkeeping skill, "Grain"). A cross-run read would put OpenFIGI's 771,554 records back at `unit` grain, with Bookkeeping's statements on every bundle (ticket 239 removed them).

Route: **the SEC ticker file is read by OpenFIGI's own run.**
1. The SEC's `company_tickers_exchange` file is placed, as an additive copy with its receipt, in the OpenFIGI capture folder. It is already on this machine (the `sec.submissions.company` capture), so no request is made.
2. OpenFIGI's source gains a read pass over that file (`ticker`, `cik` pairs, upper-case ticker, CIK as filed) and a lookup set; `record.yaml` states `issuer_cik` with `member_value: {lookup: ..., on_many: "null"}`, so a ticker the file maps to several CIKs gives none.
3. OpenFIGI's Dataset Contract states `ISSUED_BY` with `target_key: [issuer_cik]` and `target_source: sec.company.v1`, started by the ticker file's date (observed), as Form 4 states its issuer's CIK.
4. The link resolves only when that CIK is a Company.

Cost: OpenFIGI's rules change, so its 771,554 records load again (accepted by the operator, 2026-11-16).

## Built (2026-11-16, operator: "Option 1", configuration only)

A read over a combine's pieces carries no lookups (the manifest writer builds it from the contract, the pieces and a context), so the lookup could not sit in `record.yaml`. It sits in the answers read, where lookups work, and rides through the reduce in the member:

- `sec-tickers.yaml` reads the SEC ticker file to ticker and ten-digit CIK pairs (`always: true`, one unit, so every bundle holds it).
- The answers read (`source.yaml`, three tables) makes each listing's member `<FIGI> <ticker>|<CIK>`, the CIK from a pair-set lookup that gives none where the file names none or several. A FIGI has one ticker, so the reduce still counts FIGIs.
- `record.yaml` cleans the ticker as before, ignoring what follows the bar, and states `issuer_cik` from the chosen member and `issuer_seen` from the load's `ticker_file_date` fact.
- The Dataset Contract states `ISSUED_BY` to `sec.company.v1` by `issuer_cik`, observed from `issuer_seen`.
- The load chain: OpenFIGI follows `company`, and its two steps carry the fact.
- One generic fix in the manifest writer (`read_units.companions`): a step that reads a companion beside each document asks it only of the documents its `files` match, so the ticker file can share a bundle with the answers. Failed first: `Step requests: the receipt of <the ticker file> holds no request_sha256`.

Failed before: `test_a_ticker_the_sec_file_maps_to_one_cik_states_the_securitys_issuer` (no relationship) and, end to end on PostgreSQL 16, the declared chain's links (EXA and EX-J link to their SEC Companies, EXD, two CIKs, links none). 1,416 unit and architecture tests, 2,090 mdm and engine tests and 31 OpenFIGI integration tests pass.

## Parts

- [x] 2026-11-16 10:12 ET Ruling recorded (operator words above) and the evidence counted.
- [x] 2026-11-16 12:11 ET Tests that failed first (see Built): the contract link, the companion fix, and the declared chain end to end (one CIK links, two CIKs link nothing).
- [x] 2026-11-16 12:11 ET The ticker read pass, the lookup carried in the member, `issuer_cik`, and the `ISSUED_BY` relationship in the contract, by configuration.
- [ ] The SEC ticker file copied into each OpenFIGI capture folder it loads (`openfigi/2026q2-nport`, `openfigi/form4-tickers-20261109`) with a receipt: additive, from the file already on this machine. Not done: it is part of the hosted run.
- [x] 2026-11-16 12:11 ET Mapping Document regenerated (`rules mapdoc write --only openfigi`); load chain order checked (`test_load_chain`).
- [ ] Hosted: the operator accepted the cost ("yes", 2026-11-16): OpenFIGI's 771,554 records load again. Still to be started on the operator's word to run it.
- [ ] Not covered, stays open: 6,622 Securities the SEC file does not know, and the 10,177 whose issuer's GLEIF record waits (ticket 22's mint question).
- [x] Learning → skill: `data-platform` READING.md, after `member_value`: a read over a combine's pieces takes no lookups (carry the value in the member), a file of another source rides in the capture with `always`, and a companion is asked only of the documents the step reads.
