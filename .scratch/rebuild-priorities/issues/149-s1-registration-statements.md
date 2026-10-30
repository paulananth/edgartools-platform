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
- [x] `EDGAR_IDENTITY` set (operator, 2026-10-29 21:45 ET: "set edgaridentity is my email"): kept in a private file outside Git, mode 600, loaded only for SEC commands; checked to hold an email, never printed. Was: (the SEC's User-Agent with a contact email; the capture refuses without it); checked present, never printed
- [x] The capture learns an HTML document (`text` completeness; #1230 merged 2026-10-29 21:43 ET, 20 checks green): GoF consult, tests, three-axis review, PR, CI, merge
- [x] The feed's rules (2026-10-29 22:00 ET; `rules check` ok, the acquisition and capture-target validators accept it, 464 suite tests over every source folder pass; the sequence test's answer names the new source, blocked until its target): `rules/sources/sec.registration/source.yaml` with one acquisition feed (the SEC archive's filing folders as its approved URL prefix, `sec.conditional` fetch, `text` completeness bounded by the largest main document's size, a polite rate) and a capture target (`provider.capture`); `rules check` passes
- [x] The capture's units (2026-10-29 22:00 ET, `.scratch/onboarding/sec.registration/units.py`, local files only): 9,646 filings listed, 78 with no electronic document (75 name none, 3 paper), 30 listings of a filing already listed under a co-registrant, so 9,538 units, kept outside the repo. Was: one frozen request per filing (the filing's folder plus its primary document name, scoped by CIK and accession), written from the captured submissions' index for the 9,646 S-1 and F-1 originals; nothing exists for this today (`docs/configured-capture.md`: producer manifests are Issue 20 L8 work)
- [x] Acquisition proof over 5 documents (2026-10-29 22:00 ET, `.scratch/onboarding/sec.registration/proof.py`, the capture's own transport, 5 SEC requests): 5 asked, 5 kept, 5 read back with the same hash; 0.66 to 1.44 MB each, so about 9 GB for all 9,538. The configured capture cannot prove itself: `provider.capture` runs only on a version whose proof already holds an acquisition run
- [x] The acquisition switched on in `company-on` (operator, 2026-10-29 22:02 ET: "Switch on and download (Recommended)"): version `sec.registration-2026-10-29.first-capture` saved, proven by the 5-document proof, approved on those words, active (22:05 ET)
- [ ] The capture runs in 96 bundles of 100 (the run of all 9,538 left open with 2 verified: each claim re-checks the whole run, about 4 minutes a unit). About 12 s a document: a reported unit holds the shared SEC lease until its verifier admits it, so one worker call captures one document; a fix is Bookkeeping code, not asked. Bookkeeping never gives a unit up, so a document the SEC refuses (2 so far, each 3 or more attempts) is set aside with its error and its bundle's other units go to a new run (`+`). By 2026-10-30 06:49 ET: bundles 0 to 16 complete, 1,705 documents; bundle 16 took 01:20 to 06:49 ET because the machine slept from 01:27:41 to 06:44:10 ET (power log); the driver now runs under `caffeinate -i`, which keeps idle sleep off while it runs
- [x] Decided by the operator (2026-10-30 08:49 ET): "no need to download old S-1 it makes no sense", then "2026 onwards connect to actual ticker if already launched": the capture keeps filings from 2026 on. The download stopped after bundle 23 (2,408 documents of every year saved, kept: captured files are immutable); bundle 24's run is left open, unfinished. The 661 filings from 2026 not yet captured go in 7 new bundles (`2026-0` to `2026-6`), with the 72 already saved 733 in all
- [x] Decided by the operator (2026-10-30 08:51 ET): "delete the old S-1 captures too", an exception to captured files being additive and immutable: the 2,343 captured filings from before 2026 deleted (2,341 from the bundles, 2 from the first run; about 4 GB), their list kept outside Git; 90 from 2026 kept. The 5-document acquisition proof (`proof-5`) is kept: it is the switch-on's recorded evidence. Bookkeeping's runs 0 to 23 still say verified for files no longer there
- [ ] The 2026 bundles complete (started 2026-10-30 08:49 ET, about 2.2 h)
- [x] Code authorized (operator, by 2026-10-29 22:17 ET: "make the engine read html"): the configured engine reads an HTML page
- [x] GoF consult before the first Rust edit: leave the format dispatch as one `match` arm more (2026-10-29, after 22:17 ET)
- [x] The engine reads HTML (`read.format: html`, #1233 merged 2026-10-29 22:43 ET, every check green): the page's tree built as a browser builds it (html5ever), read flat as title, text blocks and table rows (`@at`, `@table`, `@row`, cells `c1`...); 5 Rust and 3 Python tests; three-axis review fixed (stray table text, misnested tables, image titles, `colspan`, plain text, a block over 1 MiB refused)
- [x] The plain-text main documents read as blocks cut at blank lines (2026-10-30 06:49 ET): of 1,244 snapshots measured, 65 are `.txt`, all read, none refused; no set-aside needed. No page hit an undefined windows-1252 byte
- [x] The registration-fee table by filing year (2026-10-30 06:49 ET, 1,244 snapshots, counts only): 845 of 860 main documents filed 2001 to 2021 hold it; 2022 to 2026, 193 of 384 (it seems to move to a separate filing-fee exhibit)
- [x] Decided by the operator (2026-10-30 06:49 ET): "Main doc only (Recommended)": shares offered, price range, ticker and exchange from the prospectus cover; the aggregate offering price from the fee table where the main document holds it, else empty; no fee exhibits requested
- [ ] Capture: bronze, immutable and additive, each file with its receipt (9,646 requests; the time stated before it starts)
- [ ] Profile (data-profiling skill): fields, keys, links and quality, as REPORT.md and findings.yaml
- [ ] Onboard (data-onboarding skill): the source contract or reader, quality checks, links to Company and
  Security, Mapping Document and Data Catalog entry
- [ ] A registered offering that has launched links to its actual listed ticker (operator, 2026-10-30 08:49 ET: "connect to actual ticker if already launched"): the ticker the company now trades under, from the Security master, beside the ticker the prospectus proposed
- [ ] Silver table spec and landing through the silver writer
- [ ] Tests, the operator's approval of the rules, switch-on
- [ ] Learning → skill
