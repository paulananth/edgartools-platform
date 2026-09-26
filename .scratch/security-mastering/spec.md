# Mastering of securities

Status: ready-for-agent

## Problem Statement

A security is stored twice, and neither copy is the instrument. A 13F row mints one Security from a CUSIP. A Form 4 mints another from an issuer and a title, with no CUSIP. Alphabet Class A and Class C become dozens of rows because the filed title and the issuer spelling vary. An ETF share is treated as if BlackRock, Vanguard, or SSGA issued it, while the filing names the trust. The operator cannot see one Security, the company or trust that issued it, and the person or fund that holds it.

## Solution

Master securities from 13F. One CUSIP is one Security. The display title is the normalized class, or Option when the filing is an option. `ISSUED_BY` points at the mastered issuer: the Company for an operating-company share, and the Fund Company (the trust that files) for an ETF share. A Form 4 that names the class attaches to that Security. It does not create another one. The adviser manages the fund series and is not the issuer.

## User Stories

1. As an operator, I want one Security per 13F CUSIP, so that a share class is an instrument and not a spelling of a title.
2. As an operator, I want Alphabet Class A (`02079K305`) and Class C (`02079K107`) to be two Securities of one Company, so that the two classes are not collapsed.
3. As an operator, I want the Security to exist before its issuer is known, so that a CUSIP is kept while the Company match waits.
4. As an operator, I want a 13F issuer string not to mint a Company, so that an unmatched name stays evidence.
5. As an operator, I want the Security Title to be the normalized class, so that `CAP STK CL A`, `CL A`, and `CLASS A` are Class A.
6. As an operator, I want a title that does not name the class, such as `COM`, not to win, so that Class A and Class C stay distinct.
7. As an operator, I want a CUSIP filed as `OPTIONS` to be titled Option, so that it does not inherit Class A from the same issuer.
8. As an operator, I want a title that names neither a class nor a kind to wait, so that a bare "Common Stock" does not choose between two classes.
9. As an operator, I want each holding to keep the title and issuer name the manager wrote, so that the filed words survive beside the master title.
10. As an operator, I want `ISSUED_BY` to point at the mastered Company, so that `GOOGLE INC` and `ALPHABET INC` are one issuer.
11. As an operator, I want an ETF share's `ISSUED_BY` to point at the Fund Company, so that `ISHARES TR`, `VANGUARD INDEX FDS`, and `SPDR S&P 500 ETF TR` issue their own CUSIPs.
12. As an operator, I want BlackRock, Vanguard, and SSGA to manage the series, so that the adviser is not recorded as the issuer.
13. As an operator, I want N-CEN to name that adviser, so that the manager does not come from the 13F issuer string.
14. As an operator, I want the fund series to hold other Securities, so that an ETF portfolio is a holding and not an issue link.
15. As an operator, I want a Form 4 that names the class to attach to the existing CUSIP Security, so that "Class A Common Stock" does not create a third Security for `02079K305`.
16. As an operator, I want a Form 4 "Common Stock" to wait when the Company already has Class A and Class C, so that mastering does not guess.
17. As a person, I want my reported shares to be a holding of a Security, so that the position is not a field of me or of the Company.
18. As a person, I want not to be the issuer, so that `ISSUED_BY` never starts at a Person.
19. As an operator, I want the 13F reader to emit the CUSIP, the filed title, and the filed issuer name only, so that reading the table does not itself create the Security.
20. As an operator, I want a name-only match of `ISHARES TR` to BlackRock to be rejected, so that company mastering's CIK rule is not bypassed.

## Implementation Decisions

- Securities mastering consumes 13F evidence. The identity key is the CUSIP. The Security Title is derived only from the titles filed for that CUSIP.
- A class token (`CL A`, `CLASS A`, `CAP STK CL A`) becomes Class A, Class B, or Class C. An options token becomes Option. Any other title leaves the Security Title waiting.
- The filed title and the filed issuer name stay on the holding. They are not the identity.
- `ISSUED_BY` is written only when the issuer resolves to an existing mastered Company or Fund Company. The 13F string never creates that party.
- Fund Company resolution is the CIK of the registrant that files. `ISHARES TR` is that registrant. BlackRock is the adviser from N-CEN and is `MANAGES_FUND`, not `ISSUED_BY`. The same split holds for Vanguard and SSGA.
- Form 4 evidence attaches only when the issuer Company is known and the title names a class that already has exactly one CUSIP for that Company.
- A person's shares are Holdings from the Person to the Security. The person's office is not part of securities mastering.
- The 13F contract reader emits `cusip`, the filed title, and the filed issuer name. Securities mastering is a later publication, not that reader.
- The test seam is one publication: accepted evidence in, the set of Securities and their `ISSUED_BY`, Holdings, and `MANAGES_FUND` edges out.

## Testing Decisions

- A good test asserts the published Securities and edges. It does not assert parser steps or the Company CIK-to-LEI matcher.
- The proving bundle contains Alphabet Class A and Class C rows under both `ALPHABET INC` and `GOOGLE INC`, with titles `CAP STK CL A`, `COM`, and `CL A`; the options CUSIP `02079K907`; iShares CUSIP `464287200`, Vanguard CUSIP `922908363`, and SPDR CUSIP `78462F103` with their trust names; an N-CEN adviser row for BlackRock on the iShares series; one N-PORT holding by that series; a Form 4 "Class A Common Stock" for Alphabet; a Form 4 "Common Stock" for Alphabet; and one person holding Class A.
- That bundle publishes three Alphabet Securities (Class A, Class C, Option). Class A and Class C are `ISSUED_BY` Alphabet. The three ETF CUSIPs are `ISSUED_BY` their trust Fund Companies. BlackRock `MANAGES_FUND` the iShares series. The series holds the portfolio Security. The Form 4 class row attaches to `02079K305`. The bare "Common Stock" row does not attach. The person holds Class A and does not issue it.
- A result that points `464287200` at BlackRock fails.
- Prior art is the contract test that checks one information-table row, and the master-data tests that assert entities and relationships rather than helper functions.

## Out of Scope

- Building the N-CEN or N-PORT parsers. Mastering consumes that evidence once it exists.
- Company CIK-to-LEI matching and the Company completion gate.
- Replacing the production 13F parser.
- Minting a Security from a Form 4 when the Company has no 13F CUSIP.
- OpenFIGI or any other CUSIP bureau.
- A Person as an issuer.
- Offices, audit engagements, parents, branches, and venues.
- Gold tables and the decision graph.

## Further Notes

Company mastering confirms a rename because it is one CIK. It does not confirm that a trust is its sponsor. Securities mastering must not invent that jump.
