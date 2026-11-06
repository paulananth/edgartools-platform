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
Rules handoff. Both controlled replays completed: 2.6 minutes for registrants,
43.3 minutes for funds. Governed current readings and mastered links confirmed
12,937 valid IS_SUBFUND_OF relationships to 1,245 Company registrants. Every
relationship period starts at its captured filing observation, has observed
basis and retains the provisional marker. All 12,937 series readings and all
1,947 registrant readings retain their expected quality flag and identity
fields. The normal repeat selected zero new documents for both sources.

Native OpenMetadata readback confirms one typed Fund Series → Fund Company
edge, qualified descriptions on both terms, the relationship asset and both
source assets, and two externally executed quality results: 12,937 of 12,937
series and 1,947 of 1,947 registrants flagged for unknown authoritative start.
Those failed checks leave the approved provisional relationships valid. No
Shared domain or glossary exists. This was a scoped API update preserving
unrelated metadata; the broader unsupported-edge publisher defect remains
tracked separately in issue #1447. Readback compares decoded description text
because the native sanitizer encodes the equals sign as an HTML entity.

The captured-data load and native readback used code at 29ff6dd1. Rebase onto
current main changes only unrelated issue notes and the provisional-date skill;
range-diff confirms the source implementation is identical. The two activated
source digests still match the committed files. Actual source records and
private evidence remain outside this public repository.

Ready PR #1454 carries the two source approval entries at their exact digests
and the operator's exact words. The finalization reference takes effect when
that PR merges; live activation had already used captured-data proof. All
current rules have a listed approval; the seven approval tests pass.
