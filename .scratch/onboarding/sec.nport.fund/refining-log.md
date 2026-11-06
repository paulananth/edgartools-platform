# N-PORT series/registrant provisional start

Operator, 2026-11-06: "make it valid with the file date until we fix the data
quality reflect this in open metadata". This replaces the earlier "Funds now,
link later" deferral; it does not assert that the filing date is inception.

The source field is `SUBMISSION.FILING_DATE`. The retained date is already
joined into each series' latest filing. The contract now supplies it as an
observation time, leaving `authoritative_start` unknown. The common engine
therefore records `valid_from_basis=observed`. The period's provisional markers
stay constant across later filings, so a changing observation does not itself
change the relationship's properties. The immutable assertion retains the
particular filing observation.

The pinned type requires a fund registration at both ends. The series gets its
registration from its filing; the Company registrant gets its first retained
filing observation so it covers all series filings in the captured scope.
Their actual registration starts remain unknown and explicitly flagged.

Captured-scope qualification reused the completed run's verified readings,
executed the changed combination and record workers with their verifiers,
normalized both source contracts and resolved endpoints with normal master
lookups. It produced 1,947 registrant records and 12,937 accepted fund records,
then 12,937 observed-date links to 1,245 Company targets, with zero reviews.
All accepted keys, identifiers, cross-references and identity fields matched
the frozen baseline mapping. Seven invalid LEI checksum refusals were unchanged.
These are preview counts, not a claim of committed links.

The new behavior test failed on the old mapping: the fund observation was
`None` instead of the filing date. The current engine passes 25 date/history
and endpoint tests, including missing and malformed first/latest registrant
dates; the affected source/catalog/mapdoc suite passes 149 tests.
Cached older extensions were refused by the current relationship vocabulary;
qualification was repeated with the extension built from this checkout.

The two tested Rules versions were saved, their captured-data proofs recorded,
approved with the operator's exact words and activated through the normal
Rules handoff. The controlled replay and final native readback remain required.
