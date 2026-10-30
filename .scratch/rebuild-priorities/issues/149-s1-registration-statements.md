# 149: S-1 registration statements: capture and process

Priority: 149. Map: [Rebuild priorities](../map.md). Opened 2026-10-29 17:20 ET (operator, 2026-10-29:
"Create a ticket to pull and process S-1").

Type: task. Status: in progress (Claude, 2026-10-29). Blocked by: none (SEC requests authorised, below).

## Question

Today the platform holds only the fact that an S-1 was filed. The captured submissions files
(`sec.submissions.company`) list each filing's form type, accession and dates, an S-1 among them. Nothing
fetches or reads the S-1 document itself.

What does "process an S-1" deliver, and how is it captured? The decisions:

- **Which forms.** The S-1 family: S-1, S-1/A, F-1 and F-1/A for a foreign issuer, S-11 for a real estate
  company, and the notice that makes a registration effective (`EFFECT`). The prospectus that follows
  (424B4 or 424B3) gives the final offering terms. Research on IPO detection
  (`docs/sec-edgar-ipo-detection.md`) reads this sequence as the signal that a company is going public.
- **What is processed.** One of these, or more than one:
  - the filing itself as an event: an IPO pipeline on Company, from registration to effectiveness to pricing;
  - the offering terms: shares offered, price range, the exchange and ticker sought, the underwriters, the
    use of proceeds;
  - the financial statements in the prospectus.
- **What is machine-readable.** Find out from the outside standards first which parts of an S-1 are
  tagged, if any (XBRL or inline XBRL), and which exist only as HTML text. The answer decides between a
  configured reader and a custom parsing step (data-platform skill).
- **Where the results go.** Company (CIK), Security (the class registered) and the financials
  (company_fact), each linked by identifier, never by copying a master field.

## Checklist

- [x] Destination ruled by the operator (2026-10-29 21:16 ET): the forms, "S-1 + F-1 originals, main doc (Recommended)" (the registration statement document only, no exhibits, amendments or drafts); what is processed, "IPO pipeline + offering terms (Recommended)" (on Company: registration filed, effective from `EFFECT` and priced from `424B4`, both already in the captured submissions; from the S-1 document: shares offered, price range, exchange and ticker sought, underwriters)
- [ ] Outside standards first (research skill, primary sources): an S-1's structure, its tagged parts
  (the SEC's EDGAR Filer Manual and its XBRL requirements), and how vendors model an IPO
  pipeline; a research note kept beside the ticket
- [x] Inventory from the files already captured (no request; 2026-10-29 21:16 ET; 6 min over the 76,230 main submissions documents of `all-76230`, the `recent` filings of each): S-1 7,849 filings by 3,364 filers, F-1 1,797 by 1,010; S-1/A 14,700, F-1/A 4,602, DRS 3,828, DRS/A 4,550, S-11 288, S-11/A 713, S-1MEF 850, F-1MEF 175; EFFECT 32,473; 424B4 4,598; 424B3 53,659. Whole submissions with exhibits: S-1 67 GB, S-1/A 94 GB, F-1 23 GB, about 400 GB for the family; the machine has 60 GB free, so the main document only. Filings only in a filer's older pages (`files`) are not counted
- [x] The operator's permission (2026-10-29 21:16 ET): "complete 149 authotised to download S-1", for the scope above
- [x] Decided by the operator (2026-10-29 21:16 ET): "Extend the configured capture (Recommended)": the configured capture (`provider.capture`, qualified for JSON) learns a size-bounded HTML document, its own PR, before the first request; every document keeps its receipt, journal event and verifier
- [ ] `EDGAR_IDENTITY` set by the operator in their own environment (the SEC's User-Agent with a contact email; the capture refuses without it); checked present, never printed
- [ ] The capture learns an HTML document: GoF consult, tests, three-axis review, PR, CI, merge
- [ ] Capture: bronze, immutable and additive, each file with its receipt
- [ ] Profile (data-profiling skill): fields, keys, links and quality, as REPORT.md and findings.yaml
- [ ] Onboard (data-onboarding skill): the source contract or reader, quality checks, links to Company and
  Security, Mapping Document and Data Catalog entry
- [ ] Silver table spec and landing through the silver writer
- [ ] Tests, the operator's approval of the rules, switch-on
- [ ] Learning → skill
