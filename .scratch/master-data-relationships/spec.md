# Master data domains and relationships

Status: ready-for-agent

## Problem Statement

An operator cannot tell, from one place, how a Person, a Company, a Security, and a Fund Series connect. The running master data store uses a second set of names for the same facts, and it creates two Securities for one instrument: one from a 13F CUSIP and another from a Form 4 title. ETF shares get pointed at the adviser (BlackRock, Vanguard, SSGA) even though the filing names the trust. A person who is an officer, a holder, and an adviser looks like three people.

## Solution

Publish one set of master data domains and one set of relationships. A Security is one 13F CUSIP. A Person is one natural person, and every office, holding, and fund-management fact is a relationship on that person. An ETF share is issued by the Fund Company that files, and the adviser manages the series.

## User Stories

1. As an operator, I want eight master data domains, so that Company, Person, Security, Fund Structure, Branch, Government Entity, International Organization, and Market/Venue are the only identities.
2. As an operator, I want Adviser, Audit Firm, and Fund to be profiles, so that a registration does not create a second identity.
3. As an operator, I want one Security per 13F CUSIP, so that Alphabet Class A (`02079K305`) and Class C (`02079K107`) are two Securities of one Company.
4. As an operator, I want the Security to exist before its issuer is known, so that a CUSIP is not dropped while the Company match waits.
5. As an operator, I want a 13F issuer string not to mint a Company, so that an unmatched name stays evidence.
6. As an operator, I want the Security Title to be the normalized class, so that `CAP STK CL A`, `CL A`, and `CLASS A` are Class A.
7. As an operator, I want a title that does not name the class, such as `COM`, not to become the Security Title, so that Class A and Class C stay distinct.
8. As an operator, I want a CUSIP filed as `OPTIONS` to be titled Option, so that it does not inherit Class A from the same issuer.
9. As an operator, I want a title that names neither a class nor a kind to wait, so that a bare "Common Stock" does not pick between Class A and Class C.
10. As an operator, I want each holding to keep the title and issuer name the manager wrote, so that the filed words survive next to the Security Title.
11. As an operator, I want `ISSUED_BY` to point at the mastered Company, so that `GOOGLE INC` and `ALPHABET INC` are one issuer.
12. As an operator, I want an ETF share's `ISSUED_BY` to point at the Fund Company, so that `ISHARES TR`, `VANGUARD INDEX FDS`, and `SPDR S&P 500 ETF TR` issue their own CUSIPs.
13. As an operator, I want BlackRock, Vanguard, and SSGA to `MANAGES_FUND` the series, so that the adviser is not the issuer.
14. As an operator, I want N-CEN to be the evidence of that adviser, so that the manager name comes from the census and not from a 13F issuer string.
15. As an operator, I want N-PORT to be the Fund Series holding other Securities, so that an ETF portfolio is Holdings and not `ISSUED_BY`.
16. As an operator, I want a Form 4 that names the class to attach to the existing CUSIP Security, so that "Class A Common Stock" does not create a third Security.
17. As a person record, I want one Person Identity, so that officer, holder, and adviser facts do not split me.
18. As a person record, I want an Adviser Profile on myself, so that an individual adviser registration is not a second person.
19. As a person record, I want `EMPLOYED_BY` a Company, so that my office is a relationship with a Relationship Capacity: director, officer, employee, ten percent owner, owner, or control person.
20. As a person record, I want my Form 3/4/5 office recorded as that employment, so that the old `IS_INSIDER` edge is the same relationship and not a second one.
21. As a person record, I want `HOLDS` to point at a Security, so that the shares I report are not a field of me or of the Company.
22. As a person record, I want `MANAGES_FUND` only when I have an Adviser Profile, so that a holder is not treated as a manager.
23. As a person record, I want not to be the issuer of a Security, so that `ISSUED_BY` never starts at a Person.
24. As a person record, I want not to be merged with my employer, so that employment is an edge.
25. As an operator, I want the retired `IS_PERSON_OF` and `IS_ENTITY_OF` edges gone, so that a profile is not stored as a copy of the person or the company.
26. As an operator, I want `AUDITED_BY` for one engagement, so that the auditor is not a permanent field on the Company.
27. As an operator, I want ownership parents to allow several owners, so that ownership is not accounting consolidation.
28. As an operator, I want one accounting direct parent in one scope and time, so that two selected parents are a conflict.
29. As an operator, I want a reported ultimate parent kept as the source claim, so that a calculated parent does not overwrite it.
30. As an operator, I want a calculated ultimate parent derived from accepted direct parents, so that the path and any cycle are kept.
31. As an operator, I want `IS_INTERNATIONAL_BRANCH_OF` from a Branch to its head office, so that a branch is not a subsidiary Company.
32. As an operator, I want a Market/Venue operated by a Company, and a venue hierarchy that is not ownership.
33. As an operator, I want `IS_SUBFUND_OF` and `IS_FEEDER_TO` kept as fund structure, so that they are not rewritten as `MANAGES_FUND`.
34. As an operator, I want a Company `HOLDS` and a Fund Series `HOLDS`, so that a 13F manager and an ETF portfolio are both holdings and neither is beneficial ownership by default.
35. As an operator, I want every relationship to carry its Relationship Interval, so that an office or a holding can stop and start again.
36. As an operator, I want the 13F reader to emit the CUSIP, the filed title, and the filed issuer name only, so that reading the table does not create the Security or `ISSUED_BY`.

## Implementation Decisions

- One relationship catalog uses the glossary names. `IS_INSIDER` is the old name of `EMPLOYED_BY` for a Form 3/4/5 office and is not a second relationship. `COMPANY_HOLDS` and `INSTITUTIONAL_HOLDS` are Holdings. `IS_PERSON_OF` and `IS_ENTITY_OF` are not published.
- A Security is created from a 13F CUSIP. The Security Title is derived from the filed titles of that CUSIP: a class token becomes Class A, Class B, or Class C; an options token becomes Option; anything else waits. The raw title and issuer name remain on the holding.
- `ISSUED_BY` is written only when the issuer resolves to an existing mastered Company or Fund Company. A 13F issuer string never creates that Company.
- Fund Company resolution is by CIK of the registrant that files, not by a fuzzy match from `ISHARES TR` to BlackRock. The adviser link is `MANAGES_FUND` from the N-CEN investment adviser to the Fund Series.
- Form 4 evidence attaches to a Security only when the issuer Company is known and the title names a class that already has one CUSIP for that Company. The prototype 13F contract already emits `cusip`, `security_title`, and `issuer_name` and stops there.
- Relationship Capacity is a property of `EMPLOYED_BY`, not a separate identity.
- The test seam is one publication: accepted evidence in, the set of identities and relationships out. Parser internals and the Company CIK-to-LEI match are not a second seam.

## Testing Decisions

- A good test feeds a fixed bundle of evidence and asserts the published identities and edges. It does not assert private matcher steps.
- The bundle that proves the map contains: Alphabet Class A and Class C 13F rows under both `ALPHABET INC` and `GOOGLE INC` with mixed titles (`CAP STK CL A`, `COM`, `CL A`); the options CUSIP `02079K907`; one iShares, one Vanguard, and one SPDR CUSIP with their trust names; an N-CEN adviser row for BlackRock on the iShares series; an N-PORT holding of another Security by that series; a Form 4 "Class A Common Stock" for Alphabet; a Form 4 "Common Stock" for Alphabet; a person who is an officer, a holder, and an adviser.
- Expected edges from that bundle: two Alphabet Securities plus one Option; `ISSUED_BY` Alphabet for the share classes; the options CUSIP titled Option; ETF Securities `ISSUED_BY` the trust Fund Company; `MANAGES_FUND` from BlackRock to the series; Holdings from the series to the portfolio Security; the Form 4 class row attached to `02079K305` and the bare "Common Stock" row not attached; one Person with `EMPLOYED_BY`, `HOLDS`, an Adviser Profile, and `MANAGES_FUND`.
- Prior art is the contract test that already checks one information-table row, plus the master-data publication tests that assert entities and relationships rather than parser helpers.
- A name-only match of `ISHARES TR` to BlackRock fails the test.

## Out of Scope

- Building the N-CEN or N-PORT parsers. The spec consumes their evidence once it exists.
- Company CIK-to-LEI matching, GLEIF parent rules, and the Company completion gate.
- Replacing the production 13F parser. The contract reader stays a column emitter.
- Minting a Security from a Form 4 when the Company has no 13F CUSIP. That case was not accepted.
- OpenFIGI or any CUSIP bureau. The 13F filing remains the CUSIP register.
- A Person as an issuer. Branch and Person issuer publication stay deferred.
- Gold tables, the decision graph, and ticker lookup.

## Further Notes

Company mastering confirms a rename (`GOOGLE INC` to `ALPHABET INC`) because it is one CIK. It does not confirm that a trust is its sponsor. `ISSUED_BY` for an ETF share stays on the Fund Company. The sponsor is `MANAGES_FUND`.
