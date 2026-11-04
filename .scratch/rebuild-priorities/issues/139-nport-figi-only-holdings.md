# 139: N-PORT holdings filed with only a FIGI find their Security

Priority: 139. Map: [Rebuild priorities](../map.md). Opened 2026-10-27 16:50 ET.

Type: task. Status: resolved (2026-11-04 13:44 ET) by the PR that carries this line; the question of asking OpenFIGI for the 5,892 FIGIs no Security holds is deferred.
Blocked by: none. Comes from [138](138-one-security-mastering-by-cross-reference.md)'s
N-PORT FIGI line (operator, 2026-10-27: "Drop the rule, new ticket (Recommended)").

## Why

N-PORT files a FIGI in `OTHER_IDENTIFIER` (descriptions such as "FIGI",
"BBGID", "Bloomberg identifier"). Measured on 2026 Q2, counts only (ticket 138):

- 16,600 holdings file a valid FIGI. Only 508 of them also carry a CUSIP or an
  ISIN, so only those make an N-PORT Security record today. Of the 508, 479 already
  sit on the Security holding their FIGI, 27 file a FIGI no OpenFIGI Security
  holds, 1 would join through it and 1 conflicts (its CUSIP wins). A FIGI rule
  on today's records changes 1 record, so 138 dropped it.
- 16,092 holdings file only a FIGI (6,026 distinct, one per holding). They make
  no Security record, so their holdings point at no Security. 1,106 of them
  (123 FIGIs) carry a FIGI an OpenFIGI Security holds.

## Parts

- [x] Decide the record (2026-11-04 13:44 ET, operator: "Yes, find only, in the second batch (Recommended)"): an N-PORT Security record keyed by its FIGI when the holding carries no CUSIP, ISIN, SEDOL or LoanX, the FIGI a cross-reference (N-PORT does not issue FIGIs; it finds and never creates or merges, Design 5); the rest wait. Built as the fourth class of ticket 190's shared key path, published in its second batch
- [ ] ~~Decide whether to ask OpenFIGI by FIGI for the 5,903 FIGIs no Security holds (a new provider request: needs the operator's permission first)~~ deferred (2026-11-04 13:44 ET): not asked. Counted today (2026 Q2, counts only): 16,058 holdings are keyed by a FIGI alone, 6,015 distinct FIGIs, of which 123 are held by an OpenFIGI Security and 5,892 are not; 1,605 more holdings file a FIGI beside another key, which is not read. The answer to ticket 126's sample (55 of 100 answered by OpenFIGI) is the nearest evidence of what asking would return
- [x] Source extract, Dataset Contract and a find-only rule (2026-11-04 13:44 ET): `identifiers.yaml` reads the FIGI rows (labels FIGI, BBGID, Bloomberg identifier and ID_BB_GLOBAL; the fund's INTERNAL and USER DEFINED values are its own), the key coalesces carry `figi` after the LoanX, `key_kind` names it, the contract files it as a cross-reference (`cross_references: {figi: figi}`), and `nport-security-figi` (`on_no_match: wait`, only a record whose `key_class` is `figi`) is in `rules/merge/policy.yaml`, switched on on the operator's word (the option he chose read "switched on after a limited test under your standing approval"). Counts file `.scratch/rebuild-priorities/research/139_limited_test.json` (sha256 c52bf9ac...2ddb)
- [x] The silver holding row takes the Security its FIGI finds (2026-11-04 13:44 ET): the row's `security_key` coalesces the FIGI after the other keys (holding-rows.yaml), so a FIGI-keyed record bound to a Security gives the row its link, and an unbound one gives none
- [x] Tests (2026-11-04 13:44 ET): `tests/integration/test_nport_sedol_loanx.py` (a FIGI-only holding is a find-only record in the second batch, a FIGI beside a CUSIP never keys), `tests/integration/test_nport_security_other_keys.py` (the held FIGI binds to its Security and creates nothing, an unheld FIGI waits); three-axis review by the author inline (rules and tests only); PR, CI and merge: the PR that carries this line
- [x] Learning → skill (2026-11-04 13:44 ET): `skills/security-master/SKILL.md` (the key order, FIGI the find-only fourth class)
