# Company phase 2 and Gold acceptance

## Destination

Gold is accepted: after one hosted load, `dbt test` as the Gold writer passes every link test, where each link resolves 100% of
its in-scope rows to exactly one master and a row is out of scope only when its key is Set Aside (CONTEXT.md).

## Notes

Measured on `aws-20261127` (counts from the hosted stores, read-only, 2026-11-27):

- The company feed read 76,230 filers, stored 6,474 and held 69,756 back (`classification_deferred`): step 0 of
  `sec-company-candidate` defers a filer with no ticker (operator, 2026-11-09: "For phase 1 master only publically traded
  companies (filter)").
- Gold's company links name 5,864 distinct CIKs; 976 had no `sec.company.v1` binding (853 never mastered, 123 companies only
  through N-CEN or N-PORT). After this effort's rule 691 of them resolve through the company feed and 102 more through the CIK
  on any company master.
- Registration tickers: 572 distinct, 200 on a Security; nothing creates a Security from a registration statement's ticker,
  and every Security ticker arrives through OpenFIGI answers. 365 tickers sit on more than one Security (a US and a foreign
  listing); 726 of those 742 Securities carry listing MICs.
- After the finish, the mirror held none of its rows until `REFRESH_MIRROR` (hosted-load-aws ticket 10, merged).

## Decisions so far

Operator, 2026-11-27, one question at a time (grilling):

1. Phase 2, not phase 1's scope in the tests ("phase 2").
2. `operating` filers without a ticker become companies, and `other` filers that are not people too ("a and b").
3. An `other` filer is a company by a legal-form word in its name, from the person rule's `entity_legal_form` list: 33,203
   filers, none also a person ("agreed").
4. A fund-named `other` filer is Set Aside as a probable fund structure; a fund-structure rule for SEC filers is its own later
   step ("a and c").
5. A Form-D-only filer with a legal-form word and no fund word is Set Aside with no Probable Kind; the fund-structure step decides
   it by Form D's industry group ("agreed").
6. An `investment` filer is a company (the Fund Company), decided before the fund-word test ("agreed").
7. A Gold link resolves by its identifier (CIK, ticker) on any master of its kinds, whichever feed mastered it ("agreed").
8. Commodity pools (SIC 6221) stay Set Aside as probable fund structures ("agreed").
9. A link may name several kinds: `[company, fund_structure]` for an issuer, `[person, company]` for a reporting owner ("agreed").
10. Gold's test leaves out a key the Set Aside table holds; every other row resolves, 100%, to one master ("agreed").
11. OpenFIGI is asked about the registration tickers MDM lacks, about 372 (operator's permission for that request: "agreed").
12. A ticker several Securities hold resolves among US listings ("agreed, however uniquify with venue or exchange").
13. The cover's exchange wording maps to a MIC through an RDM code set over RDM's ISO 10383 MICs ("we already have mic in rdm");
    the match is at the operating MIC, then the `US` ISIN ("agreed").
14. Glossary: Mastering Scope, Set Aside, Trading Venue ("agreed").
15. One ticket and PR per piece, proved locally; one hosted load at the end ("agreed").

## Not yet specified

- The fund-structure rule for SEC filers (fund-named, Form-D-only by industry group, commodity pools): its own grilling.
- Two Gold CIKs the company feed never saw: traced in ticket 07.

## Out of scope

- Mastering a Security from the SEC ticker file: it stays a lookup (operator, 2026-11-16, `sources/openfigi/sec-tickers.yaml`).
- Declared shares below 100% for a link.
