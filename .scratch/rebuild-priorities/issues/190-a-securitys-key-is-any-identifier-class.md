# 190: A Security's key is any identifier class, not CUSIP or ISIN only

Switch-on: standing approval (operator, 2026-11-04 07:00 ET: "switch on for form 4 keep it standing approval for ticket 190 191"): it is switched on once its limited test passes, with the counts recorded here and no question asked.

Priority: 190. Map: [Rebuild priorities](../map.md). Opened 2026-11-04 01:44 ET, from [ticket 125](125-securities-and-funds-uniquely-identifiable.md) (operator, 2026-11-03: "yes do option 1 and open the follow-up ticket").

Type: task. Status: approved to build (operator, 2026-11-04 06:46 ET: "approve 190 and 191"). Blocked by: [125](125-securities-and-funds-uniquely-identifiable.md) (its SEDOL and LoanX join slice, which this follows).

## Question

Ticket 125 lets a SEDOL or a LoanX **join** the Security a holding already keys by its CUSIP or ISIN. It does not let one **create** a Security when a holding carries neither a CUSIP nor an ISIN: the engine reads the key class from three places that each know only CUSIP and ISIN, so adding a class copies about six files (the source's key tables, the reduction groups, the combination, the Identifier Contracts, the verification test and the mapping documents).

Make the key class a configured list (each class with its Identifier type, its table and its label), so that adding the third class is a rules change and one test, and a Security with only a SEDOL or a LoanX is created.

## Parts

- [x] Count (2026-11-04 08:33 ET, 2026 Q2 file, counts only): of 5,347,869 holdings, 999,207 carry neither a valid CUSIP nor a valid ISIN; of those 2,011 carry a valid SEDOL (1,122 distinct). Corrected (2026-11-04 09:42 ET): the LoanX count above, 416 holdings and 377 distinct, read only the label LOANX; the engine's rule also reads LOANX ID and LOAN X ID, which gives 2,238 distinct LoanX keys. So at most 3,360 Securities would be keyed (1,122 SEDOL and 2,238 LoanX); of the SEDOL keys 1,065 (95%) are also filed beside a CUSIP or ISIN on another holding, and of the LoanX keys 202 (9%), so those join an existing Security instead of creating one: about 57 new SEDOL Securities and 2,036 new LoanX ones
- [x] GoF consult (2026-11-04 09:19 ET): the key class was repeated by hand because the rules language has no loop; copying the ISIN-only table per class was refused by the operator ("You can not build every make isin work for others don't be dumb", then "Always build generic make it a rule", now in AGENTS.md). Built as one shared path instead: the branch for a holding with no CUSIP is renamed `no_cusip` (tables, groups, columns; no behaviour change, 29 N-PORT tests before and after) and its key is the first of ISIN, SEDOL, LoanX
- [x] The key path is shared (2026-11-04 09:19 ET): `security_no_cusip`, `no_cusip_class` (source.yaml), `no_cusip_issuer` (issuers.yaml) and the holding row's `security_key` (holding-rows.yaml) each take the key as a coalesce over the ISIN, SEDOL and LoanX lookups, `key_kind` names the class, `record.yaml` gives the identifier of that class. Limit, stated: the rules language has no list, so a fourth class is a lookup set plus one line in those coalesces; an engine key-class list is deferred until a fourth class is wanted
- [x] Tests on invented data (2026-11-04 09:19 ET, `tests/integration/test_nport_sedol_loanx.py`): a SEDOL-only holding creates one Security keyed by it, a second holding with the same SEDOL joins it (5 records from 7 holdings), a LoanX-only holding creates one, and a holding with a CUSIP or an ISIN keeps that key whatever else it files. The old test asserting no Security for a SEDOL-only holding would fail now
- [ ] Finding (2026-11-04 09:42 ET): in one batch, records do not match each other, so a SEDOL-keyed record loaded with its CUSIP's record makes a duplicate Security (7 Securities, not 5, in either order of one batch; the record joins only when the CUSIP's Security was published in an earlier batch). A SEDOL filed beside a CUSIP must also never match (a rule on every record's SEDOL merged two CUSIP Securities that share one; 1,590 of 26,081 SEDOLs sit on several keys, at most 4): the rule is restricted to records whose key class is the SEDOL (`field_in_set@1` on `provenance.matching.key_class`, built and tested). Needs the operator's decision: the keyed records are published in a second batch after the CUSIP and ISIN records, as the Form 4 symbols are after OpenFIGI
- [ ] The Identifier Contracts verified on a test run (no identifier on two Securities); approved under the standing approval
- [ ] Mapping documents regenerated; the whole CI set
- [ ] PR, CI green, merged on green
- [ ] Learning → skill (`security-master`; `data-onboarding`, the gaps table)
