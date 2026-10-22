# 01 Research: how outside standards name a share class

Gathered 2026-10-22 for ticket 130 (a Security's share class), which tickets 24
and 25 wait on (operator, 2026-10-22: "Research the class rule now"). Public
sources only, found by web search; no provider site was requested. Where a
vendor's practice is known only in general, it is marked **unverified**. Later
Security decisions read this note first.

## Sources at a glance

| Source | What it says about a class | Public? |
|---|---|---|
| SEC Form 4, General Instruction 3(b) | The title "should clearly identify the class, even if the issuer has only one class"; examples "Common Stock", "Class A Common Stock", "Class B Convertible Preferred Stock"; one line per class | Yes (form4.pdf) |
| SEC Official List of Section 13(f) Securities | One CUSIP per line with CUSIP Global Services' standard description ("CL A", "COM", "CAP STK CL A" in the filed data); the descriptions are CGS's, not the SEC's | Yes (quarterly PDF); the abbreviation legend was not found |
| ISO 10962 (CFI), group ES (common shares) | Six letters: voting right (V, N, R, E), ownership restriction (T, U), payment status, form. **No class letter**: Class A and Class C differ only when their voting differs | Attribute tables public; text paywalled |
| ISO 18774 (FISN), ANNA abbreviation list | A short name of issuer and description, built on the CFI groups; whether "CL A" is a listed abbreviation was not verified | List public (ANNA, 2025-06) |
| OpenFIGI | A share-class FIGI at the top of its hierarchy (share class > composite > exchange FIGI); `securityType` "Common Stock"; no class-letter field found | Third-party dictionaries |
| CRSP stock files, SHRCLS | A share-class letter beside the issue (blank for a single class), as remembered; **unverified**, the definition is behind WRDS | No |
| FactSet, Bloomberg | Share-class level in their symbology; class in the security's name (**unverified**) | No |

## What follows

- **No standard code list of class letters exists.** CFI codes voting, not the
  letter; FIGI gives each class its own id but no letter. The class is the
  letter the issuer gave it, as the filed title states it (Form 4 3(b); CGS
  descriptions). CRSP's practice, if as remembered, is the same: a letter, blank
  when there is one class.
- **The CUSIP already tells classes apart.** Each class has its own CUSIP and
  share-class FIGI; the letter is the bridge only for a filing that carries no
  CUSIP, such as a Form 4.
- **A title that names no class says nothing about which class.** Form 4's own
  instruction asks for the class, but "Common Stock" is filed for a single-class
  issuer and, against the instruction, for a multi-class one.

## Measured on the local copies (no request left the machine)

| Data | Count |
|---|---|
| N-PORT 2026q2 equity holdings (asset category EC): distinct CUSIPs | 24,946 |
| of which a filed title names a class (CL, CLASS or CLS, then one letter) | 1,431 (5.7%) |
| of which filers name two different letters for one CUSIP | 15 |
| issuers (by LEI) with two or more equity CUSIPs | about 2,400 |
| of which their CUSIPs carry two or more class letters | 48 |
| Form 4 cohort (3,398 filings, 63 issuers): common-stock rows | 9,495 |
| of which the title names a class | 5,283 (56%), from 6 issuers |
| issuers whose Form 4 titles name two classes | 1 |

So the letter is rare on a Security (6% of equity CUSIPs) and, where it exists,
almost always agreed (15 conflicts in 1,431). An issuer with several equity
CUSIPs is common (about 2,400), so "the issuer's only equity Security" is no fallback
for a bare "Common Stock": the extra CUSIPs are listings, units, rights and
depositary receipts, not classes.
"Series" is left out of the class tokens: with it, 45 more CUSIPs matched;
how many of those are preferred series rather than common classes was not
measured.

Sources: [SEC Form 4](https://www.sec.gov/divisions/corpfin/topic-topics/forms/form4.pdf),
[13(f) list 2024q2](https://sec.gov/files/investment/13flist2024q2.pdf),
[ISO 10962 (Wikipedia)](https://en.wikipedia.org/wiki/ISO_10962),
[CFI ES attributes (iotafinance)](https://iotafinance.com/en/Attributes-ISO-10962-2021-CFI-Codes-Group-ES.html),
[FISN abbreviation list (ANNA)](https://anna-web.org/wp-content/uploads/2025/06/FISN_ISO_Abbreviation-List_16.06.25_FINAL.pdf),
[OpenFIGI Security Index (Cybersyn)](https://docs.cybersyn.com/premium-public-data-products/cybersyn-enterprise/data-dictionary/openfigi-security-index).
