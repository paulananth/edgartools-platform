# 04: A Form 4 class title attaches to the CUSIP Security

Priority: 24, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/security-mastering/issues/04-form-4-attaches-by-class.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

**What to build:** A Form 4 that names the class for a Company that already has that class attaches to the one CUSIP Security. For an invented issuer with Class A and Class C, "Class A Common Stock" attaches to its Class A Security and does not create another Security. "Common Stock", when Class A and Class C both exist, waits. (Examples are invented; the repo is public.)

**Blocked by:** security-mastering 01: Publish one Security per 13F CUSIP (done); [22: ISSUED_BY a mastered Company](22-security-mastering-02-issued-by-a-mastered-company.md); [130: A Security's share class](130-a-security-share-class.md); Codex PR #1121 (the matching code it needs).

**Status:** in progress (2026-10-24 19:21 ET), Grok, branch `grok/t24-form4-security`, taken over from `claude/t24-form4-security` at `7b427867` and replayed onto `main` `3e48169f`. The Claude worktree is untouched. Waits on ticket 120's OpenFIGI first for the proving run; the next open part is the issuer-name check on the 1,285 symbols.

**Finding (2026-10-22 13:55 ET):** not configuration alone. A Form 4 names its issuer by CIK and the class in words, and carries no CUSIP; today's matching rules only match an identifier the record carries. "The issuer's Securities, narrowed to one class" is a new matching rule in code (`primitives.py`, `binding.py`, `matching.py`, `merge.py`), all four edited by #1121. Measured on the Form 4 cohort (3,398 filings, 63 issuers): 5,283 of 9,495 common-stock rows (56%) name a class, from 6 issuers; 1 issuer names two classes.

**Design (operator rulings, 2026-10-23, asked one at a time):**
- Q1, "a use lookup to resolve cusip": a Form 4 Security source record (`sec.ownership.security.v1`, one per issuer CIK and class title) is bound in the Merge Stage to the CUSIP Security; never in the silver writer.
- Q2, "(b) From MDM": the CUSIP is looked up in MDM (issuer CIK → Company → ISSUED_BY → its Securities), not from captured files in the Source Extract.
- Q3, "agreed": plain "Common Stock" binds when the issuer has one common-stock share-class FIGI only; with two or more it waits for review.
- Q4, "first priority openfigi second priority can be 13F, n-port is last": a Security is common stock by OpenFIGI's security type first, then the class title filed in 13F, then N-PORT's. OpenFIGI separates classes by share-class FIGI, but its name gives a letter for only 284 of 4,752 common-stock CUSIPs (local capture), so the letter is `share_class` (ticket 130).
- The rule never makes a Security; no match, two classes or an unknown letter waits for review. "design is correct" (2026-10-23 20:28 ET).

- [x] The design, the operator's rulings above (2026-10-23 20:28 ET)
- [ ] Measured on the Form 4 cohort before code: lines that bind, wait, and which evidence settled each
  - Found (2026-10-23 20:33 ET): SEC submissions state an LEI for 1 of 1,602 Form 4 issuers (the p07 ownership copy), so a CIK reaches its Securities only where its GLEIF record joined its SEC Company (ticket 22's Companies-only proof: 2,764 issuers on their SEC filer's Company, cm27 cohort). The issuer rule `gleif-issuer-lei` is declared, not switched on, and Securities wait for ticket 120's switch-on, so no store links them yet. The measurement and the Proving Run need the SEC Companies, GLEIF, and the N-PORT, 13F and OpenFIGI Securities of the Form 4 issuers together
  - Found (2026-10-23 20:31 ET): no local MDM holds Companies, Securities and ISSUED_BY together (`company-on`: 12,937 fund structures, 194 people, no Company or Security; its verifier file names a port the restarted container no longer publishes, so a read used the published port in memory). ISSUED_BY comes only from an N-PORT holding's issuer LEI through GLEIF to the Company; 13F and OpenFIGI name no issuer. The measurement needs a scoped Proving Run on a disposable PostgreSQL 16: the 63 issuers' SEC Companies, GLEIF, and their N-PORT, 13F and OpenFIGI Securities
  - Found (2026-10-23 20:58 ET), after the operator's note "Securities should be driven from openfigi": 1,702 Form 4 issuers in the p07 copy file a trading symbol (100 more than file a non-derivative line); for 1,285 (75%) the symbol finds exactly one OpenFIGI US common-stock share-class FIGI and one CUSIP in the 2026q2-nport OpenFIGI capture; 417 symbols are not in that capture (it holds only CUSIPs N-PORT asked); 5 issuers have sibling class tickers. Asked: may the rule bind by symbol to the Security's OpenFIGI ticker (the 2026-10-14 ruling keeps ticker lookup only)
- [x] Route changed to OpenFIGI (2026-10-23 21:36 ET): operator, 2026-10-23, "Securities should be driven from openfigi", then "agreed" to the recommendation read as yes to finding a Form 4's Security by its filed trading symbol through the OpenFIGI ticker; "make the seurities run should process openfigi first" is built on ticket 120 (branch `claude/t120-openfigi-first`), so every found Security carries OpenFIGI's ticker. The GLEIF route above is set aside
- [ ] Before the rule: the symbol finds the right issuer: of the 1,285, how many OpenFIGI names agree with the Form 4 issuer's name, by filing year (tickers are reused); and whether `openfigi_ticker` can be matched (today a cross-reference, refused as a binding namespace by contract registration), which is a measured proof, not a deterministic one
- [ ] GoF consult on the matching code
- [ ] The Form 4 class recipe (deferred here from 130) and the Dataset Contract `sec.ownership.security.v1`
- [ ] The matching rule (a new versioned primitive): a class title binds to that letter's Security
- [ ] That attachment does not add a Security (no mint; Security count unchanged)
- [ ] Plain "Common Stock" binds with one common-stock share-class FIGI, waits with two or more
- [ ] Nothing matching waits for review
- [ ] `ownership_line`'s Security link through the new source record
- [ ] Proving Run on a disposable PostgreSQL 16, counts per kind of evidence
- [ ] Switch-on on the operator's words
- [ ] Three-axis review, PR, CI green, merge
- [ ] Learning → skill (so far, 2026-10-23 20:33 ET: `skills/security-master/SKILL.md`, an SEC filer reaches its Securities only through GLEIF; `skills/data-platform/LOCAL-TESTING.md`, a restarted container's new port)
