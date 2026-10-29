# 149: S-1 registration statements: capture and process

Priority: 149. Map: [Rebuild priorities](../map.md). Opened 2026-10-29 17:20 ET (operator, 2026-10-29:
"Create a ticket to pull and process S-1").

Type: task, gated (needs SEC requests). Status: open. Blocked by: the operator's permission for each SEC
request (map, standing rules).

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

- [ ] Destination ruled by the operator: which forms, and what "processed" delivers (the decisions above)
- [ ] Outside standards first (research skill, primary sources): an S-1's structure, its tagged parts
  (the SEC's EDGAR Filer Manual and its XBRL requirements), and how vendors model an IPO
  pipeline; a research note kept beside the ticket
- [ ] Inventory from the files already captured (no request): count the S-1 family filings the captured
  submissions list, by form and by year, and how many companies filed them
- [ ] The operator's permission for each capture request, recorded here with the request and its receipt
- [ ] Capture: bronze, immutable and additive, each file with its receipt
- [ ] Profile (data-profiling skill): fields, keys, links and quality, as REPORT.md and findings.yaml
- [ ] Onboard (data-onboarding skill): the source contract or reader, quality checks, links to Company and
  Security, Mapping Document and Data Catalog entry
- [ ] Silver table spec and landing through the silver writer
- [ ] Tests, the operator's approval of the rules, switch-on
- [ ] Learning → skill
