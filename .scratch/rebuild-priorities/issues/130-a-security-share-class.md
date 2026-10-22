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

**Status:** waiting for the operator's ruling on the proposed rule

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
- [ ] The operator rules on the proposed rule
- [ ] The class token recipe in the source extracts (13F, N-PORT, OpenFIGI none, Form 4), tested on each source's titles
- [ ] `share_class` on the Security's Dataset Contracts and merge rules; MAPPING.xlsx and security.xlsx regenerated
- [ ] The quality rule for a CUSIP with two letters
- [ ] Learning → skill
