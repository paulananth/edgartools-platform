# 130: A Security's share class

Priority: 130, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md).
Opened 2026-10-22 (operator: "Research the class rule now"), so that tickets 24
and 25 can attach a Form 4 by class once Codex's PR #1121 merges.

**Question:** what is a Security's share class, where does it come from, and
how does a Form 4 title that names a class find it?

**Research:** [01 Share-class standards](../../security-mastering/research/01-share-class-standards.md).
No standard lists class letters: ISO 10962 (CFI) codes voting, not the letter;
OpenFIGI gives each class its own share-class FIGI and no letter. The class is
the letter the issuer gave it, as the filed title states it (Form 4 instruction
3(b); the CUSIP Global Services descriptions in 13F).

**Status:** built, PR open

## Proposed rule

1. **The Security carries `share_class`, one letter**, as an MDM field. It adds
   meaning to the instrument and does not change with each filing (the MDM field
   rule, data-onboarding "Fields"). The class title stays as filed beside it.
2. **The letter comes from the titles filed for the Security's CUSIP:** "CL",
   "CLASS" or "CLS", then one letter (`CAP STK CL A`, `Class A Common Stock`).
   "Series" does not count. A title that names no class gives no letter.
3. **Filers that disagree give no letter:** the Security waits, and a quality
   rule lists it for a steward (15 of 1,431 lettered CUSIPs in N-PORT 2026q2).
4. **No RDM code set:** no standard list exists, and a letter A to Z is a
   format check, a data quality rule.
5. **A Form 4 title is read by the same rule.** A title with a letter attaches
   when its issuer has exactly one Security of that letter (ticket 24); a title
   without one waits, even for a single-class issuer, since about 2,400 issuers
   hold several equity CUSIPs (listings, units, rights, depositary receipts).

## Checklist

- [x] Outside standards researched, research note 01 written (2026-10-22 13:55 ET)
- [x] Measured on local copies: N-PORT 2026q2 equity titles and the Form 4 cohort (research note 01) (2026-10-22 13:55 ET)
- [x] The operator rules on the proposed rule: "Approve the rule (Recommended)" (2026-10-22 14:13 ET)
- [x] The class recipe in the 13F and N-PORT source extracts (N-PORT equity holdings only, by CUSIP, by ISIN and folded); the source engine equals the oracle on all 163,731 distinct local titles (`.scratch/onboarding/security-share-class/`); chain tests on invented holdings, `tests/integration/test_security_share_class.py` (2026-10-22 14:13 ET)
- [ ] ~~The class recipe for Form 4 titles~~ deferred to [24](24-security-mastering-04-form-4-attaches-by-class.md): a Form 4 Security record is built there, with the matching rule that waits on #1121
- [x] `share_class` on both Dataset Contracts; the merge rules unchanged (the default source order fills it); MAPPING.xlsx and security.xlsx regenerated, mapdoc check passed (2026-10-22 14:13 ET)
- [x] The quality rule for a Security its filers name two letters for: `share_class_one_letter`, flag only, 13F (new quality file) and N-PORT (quality v2); N-PORT, OpenFIGI, mapdoc, catalog, rules and MDM tests 1,093 passed (2026-10-22 14:13 ET)
- [x] Dry run on the local captured files, the committed chains to the Dataset Contracts: every filled letter equals the oracle's (13F 1,885, N-PORT 1,394 and 201 ISIN-only), every flag an oracle conflict, none filled and flagged (`.scratch/onboarding/security-share-class/dry-run.json`) (2026-10-22 14:52 ET)
- [x] The class from the level whose letters were counted, so a disagreeing CUSIP never takes a folded letter (`record.yaml`), test; and the Merge Stage on a disposable PostgreSQL 16 gives the mastered Security its letter, test (2026-10-22 14:52 ET)
- [x] Approval recorded under the operator's standing words "Approved the rules always" (2026-10-15), on the evidence above (2026-10-22 14:52 ET)
- [ ] ~~Two sources that disagree give no letter~~ deferred to [131](131-a-field-kept-only-when-sources-agree.md): the merge has no "agree or none" field rule (new code, after #1121); the first-ranked source wins, as for the title. 777 CUSIPs carry a letter in both sources, 1 disagrees (refining log)
- [ ] PR merged
- [x] Learning → skill: `skills/data-platform/READING.md`: keeping one token of a text with literal-marker replacements; a selection's "no" is a presence test on a missing path; a value kept only when every row agrees (select, count members, `where: {<count>: 1}`). `skills/data-onboarding/REFERENCE.md`: a contract field is a `value`, `join` or `object` (the Mapping Document refuses a computed one); a scripted rules file needs a dumper without aliases (2026-10-22 14:13 ET)
