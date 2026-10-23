# 04: A Form 4 class title attaches to the CUSIP Security

Priority: 24, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/security-mastering/issues/04-form-4-attaches-by-class.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

**What to build:** A Form 4 that names the class for a Company that already has that class attaches to the one CUSIP Security. For an invented issuer with Class A and Class C, "Class A Common Stock" attaches to its Class A Security and does not create another Security. "Common Stock", when Class A and Class C both exist, waits. (Examples are invented; the repo is public.)

**Blocked by:** security-mastering 01: Publish one Security per 13F CUSIP (done); [22: ISSUED_BY a mastered Company](22-security-mastering-02-issued-by-a-mastered-company.md); [130: A Security's share class](130-a-security-share-class.md); Codex PR #1121 (the matching code it needs).

**Status:** open, unblocked (2026-10-22 21:11 ET): 22 and 130 (#1135) are closed and #1121 merged (2026-10-22 19:08 ET)

**Finding (2026-10-22 13:55 ET):** not configuration alone. A Form 4 names its issuer by CIK and the class in words, and carries no CUSIP; today's matching rules only match an identifier the record carries. "The issuer's Securities, narrowed to one class" is a new matching rule in code (`primitives.py`, `binding.py`, `matching.py`, `merge.py`), all four edited by #1121. Measured on the Form 4 cohort (3,398 filings, 63 issuers): 5,283 of 9,495 common-stock rows (56%) name a class, from 6 issuers; 1 issuer names two classes.

- [ ] A Form 4 "Class A Common Stock" attaches to the issuer's Class A Security.
- [ ] That attachment does not add a Security.
- [ ] A Form 4 "Common Stock" does not attach while both classes exist.
- [ ] Learning → skill
