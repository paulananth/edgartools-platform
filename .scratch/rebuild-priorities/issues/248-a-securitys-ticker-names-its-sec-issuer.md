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

## Parts

- [x] 2026-11-16 10:12 ET Ruling recorded (operator words above) and the evidence counted.
- [ ] A test on a disposable store that fails first: a Security whose ticker names one CIK links to that Company; a ticker naming two CIKs, or none, links nothing; a CIK with no Company waits.
- [ ] The ticker read pass, the lookup and `issuer_cik` in OpenFIGI's reading, and the `ISSUED_BY` relationship in its Dataset Contract, by configuration; the SEC ticker file copied into the OpenFIGI capture (additive).
- [ ] Mapping Documents regenerated (`rules mapdoc write`); load chain order checked (`waits_for`).
- [ ] Hosted: the operator accepted the cost ("yes", 2026-11-16): OpenFIGI's 771,554 records load again. Still to be started on the operator's word to run it.
- [ ] Not covered, stays open: 6,622 Securities the SEC file does not know, and the 10,177 whose issuer's GLEIF record waits (ticket 22's mint question).
- [ ] Learning → skill.
