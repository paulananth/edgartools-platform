# CRD versus CIK: what each identifies, and what the platform's ADV archive actually carries

Ticket: 15. Run 2026-09-20.
Primary sources only. External quotes are verbatim from the cited URL (PDFs were text-extracted
with `pdftotext`; one WebFetch summary of SEC release 34-88760 invented quotes and was discarded in
favour of the extracted text). Repo cites are `path:line` in this worktree
(`claude/person-ticket-02`).
No Snowflake or AWS reads. Research [14](14-adv-individual-person-pipeline.md) and
[11](11-ownership-person-pipeline.md) already trace the code; this file cites them rather than
repeating.

## Sources read

External, reached:
- https://www.sec.gov/search-filings/cik-lookup — one-sentence CIK definition (corporations *and*
  individuals).
- https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/understand-utilize-edgar-cik-cik-confirmation-code-ccc
  — CIK is per filer account, permanent.
- https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/prepare-submit-my-form-id-application
  — Form ID: "company or individual", CIK issued on approval.
- https://www.sec.gov/info/edgar/ownershipxmltechspec.htm → `ownershipxmltechspec-v5-1.zip` (spec
  PDF, Sept 2015, plus `ownership{3,4,5}[A]Document.xsd.xml`, `ownershipDocumentCommon.xsd.xml`) —
  reporting-owner elements.
- https://www.sec.gov/about/forms/formadv-part1a.pdf (SEC 1707, 07-24) — Item 1.A/D/E/H, Item 3.A,
  Item 10, Schedule A/B.
- https://www.sec.gov/files/formadv-instructions.pdf (SEC 1707, 07-24, File 1 of 5) — General
  Instructions 8-9, page-header rule, Glossary 10/22/34/49/61.
- https://www.finra.org/investors/investing/working-with-investment-professional/about-brokercheck/glossary
  — "CRD Number", "CRD".
- https://www.finra.org/registration-exams-ce/classic-crd — CRD program scope.
- https://www.finra.org/investors/investing/working-with-investment-professional/about-brokercheck/faq
  — BrokerCheck derived from CRD; carries IAPD IAR data.
- https://www.finra.org/rules-guidance/rulebooks/finra-rules/8312 — BrokerCheck rule definitions.
- https://www.finra.org/rules-guidance/notices/12-10 — IAPD expanded from firms to IARs.
- https://www.finra.org/sites/default/files/AppSupportDoc/p015111.pdf — Form U4 instructions (CRD or
  IARD; Individual/Firm CRD Number fields).
- https://www.sec.gov/files/rules/sro/finra/2020/34-88760.pdf — SEC order on SR-FINRA-2020-012: CRD,
  IARD, IAPD definitions; footnotes 12-13.
- https://iard.com/ — IARD definition; FINRA operates it.
- https://www.sec.gov/about/divisions-offices/division-investment-management/electronic-filing-investment-advisers-iard
  — IAPD publishes Form ADV "except for social security numbers, certain home addresses, and contact
  employee information".
- https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data — the four bulk
  dataset families; no data dictionary.
- https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers
  — column headings = Form ADV item numbers; IARD operated by FINRA Regulation, Inc.
- https://reports.adviserinfo.sec.gov/reports/foia/reports_metadata.json — the index
  `fetch-adv-bulk` polls; 5 file families, none individual-level.
- https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/2026/ADV_Filing_Data_20260801_20260831.zip
  — the actual archive the platform downloads (7.2 MB, 100 CSV members); member list and headers
  inspected locally.
- https://api.adviserinfo.sec.gov/search/individual/<id> — undocumented IAPD search endpoint, probed
  for 4 ids (F2, labelled as an observation, not a documented fact).

External, not reachable or not usable: `sec.gov/about/forms/formadv-glossary.pdf` (404; glossary
taken from the instructions PDF instead),
`sec.gov/edgar/filer-information/how-do-i-apply-edgar-access` and `.../apply-edgar-access` (404),
`investor.gov/...check-out-your-investment-professional` (403), `federalregister.gov` (302 to an
unblock page), `adviserinfo.sec.gov/` and `/compilation` (JS shell only, no body served),
`sec.gov/page/edgar-ownership-xml-tech-spec` (5.4 draft, 404), FINRA FAQ on Form ADV/IARD (no
relevant Q&A). No SEC/FINRA data dictionary for the `ADV_Filing_Data` CSVs was found on any page
searched; column meanings below are inferred from the headers plus the SEC statement that headings
are Form ADV item numbers.

Repo: `edgar_warehouse/application/adv_bulk_fetch.py` 26, 151, 173;
`edgar_warehouse/application/adv_bulk_ingest.py` 118-129, 146-157, 237;
`edgar_warehouse/parsers/adv.py` 20, 45, 53, 57; `edgar_warehouse/mdm/adv_bulk.py` 203-207, 278-282,
292-293, 304; `edgar_warehouse/silver_schema.py` 48-62, 63-77, 89-109;
`edgar_warehouse/parsers/ownership.py` 24-39, 93-97; edgartools 5.30.0 (read-only, main repo
`.venv`): `edgar/ownership/ownershipforms.py` 932-942, 1010-1024; `edgar/entity/data.py` 477-513.

## Findings

### F1 — Issuer and scope of each identifier (Q1)

**CIK.** SEC: "The Central Index Key (CIK) is used on the SEC's computer systems to identify
corporations and individual people who have filed disclosure with the SEC." (cik-lookup). "The CIK
is a unique, publicly available number that EDGAR assigns to identify each filer account." "It is a
permanent identifier: it may not be changed and never expires." (CIK/CCC guide). Assignment is by
Form ID: "You must complete and submit Form ID … if you are a company or individual who is: Seeking
to open a new EDGAR account to file on EDGAR for the first time (a new EDGAR account number, known
as a Central Index Key or CIK, will be issued)" (Form ID guide). So the CIK's unit is the *EDGAR
filer account*, held by companies, funds, and natural persons alike; it is never retired or
reassigned per the SEC's own wording. Nothing on the pages reached says a natural person may hold
only one account (see F4).

**CRD number.** FINRA BrokerCheck glossary: "CRD Number: A unique number assigned to investment
professionals and brokerage firms as part of their registration application with FINRA." "CRD: An
online computerized system in which FINRA maintains the employment, qualification and disciplinary
histories of more than 650,000 securities industry professionals and more than 5,000 brokerage firms
that deal with the public." FINRA classic-crd: "The CRD program covers the registration records of
broker-dealer firms, branch offices and their associated individuals". Form ADV Glossary 22: "FINRA
CRD or CRD: The Web Central Registration Depository ("CRD") system operated by FINRA for the
registration of broker-dealers and broker-dealer representatives." The unit is a *registration
record*: one for a firm, one for an individual. Form U4 (the individual registration form) has
separate "Individual CRD Number" and "Firm CRD Number" fields; the archive's sole-proprietor rows
show the two are distinct numbers even when the firm *is* the individual (firm `1E1` = 343279 vs the
same person's Schedule A `OwnerID` = 8304244, F2).

**Who assigns a firm's CRD for Form ADV.** General Instruction 9: "When FINRA receives your
Entitlement Package, they will assign a CRD number (identification number for your firm) and a user
I.D. code and password … If you already have a CRD account with FINRA, it will also serve as your
IARD account; a separate account will not be established."

**Can one natural person hold both, either, or neither?** Both are possible and independent: a CIK
arises from filing with the SEC on EDGAR (an insider filing Form 4, a 13D filer); a CRD number
arises from FINRA/IARD registration (a broker rep, an IAR, or a sole-proprietor adviser's *firm*).
No source reached publishes a reference from one to the other for individuals, and Item 1.E
explicitly forbids the one place on Form ADV it could appear (F3). Retirement: SEC says CIK "never expires";
no FINRA primary page reached states whether an individual CRD number is retired or reused ("Could
not be determined").

### F2 — Firm vs individual on Form ADV, and what the platform's archive carries (Q2)

**Form fields that distinguish an individual registrant.** Item 1.A: "Your full legal name (if you
are a sole proprietor, your last, first, and middle names)". Item 1.H: "If you are a sole
proprietor, state your full residence address, if different from your principal office and place of
business address in Item 1.F." Item 3.A "How are you organized?" — "Corporation / Sole
Proprietorship / Limited Liability Partnership (LLP) / Partnership / Limited Liability Company (LLC)
/ Limited Partnership (LP) / Other (specify)". Glossary 49: "Person: A natural person (an
individual) or a company. A company includes any partnership, corporation, trust, limited liability
company ("LLC"), limited liability partnership ("LLP"), sole proprietorship, or other organization."
— so on Form ADV a sole proprietorship is a *company*, and the registrant is always the firm.

**Form fields that name natural persons inside a firm.** Item 10 / Schedule A ("Direct Owners and
Executive Officers") and Schedule B ("Indirect Owners"). Schedule A instruction 4: "In the DE/FE/I
column below, enter "DE" if the owner is a domestic entity, "FE" if the owner is an entity
incorporated or domiciled in a foreign country, or "I" if the owner or executive officer is an
individual." Instruction 7(a): "In the Control Person column, enter "Yes" if the person has control
as defined in the Glossary". Paper column set: "FULL LEGAL NAME (Individuals: Last Name, First Name,
Middle Name) | DE/FE/I | Title or Status | Date Title or Status Acquired MM/YYYY | Ownership Code |
Control Person | PR | CRD No. If None: S.S. No. and Date of Birth, IRS Tax No. or Employer ID No."
Glossary 34 defines "Investment Adviser Representative" as a class of the firm's "supervised
persons"; IARs are *not* listed on Form ADV Part 1A (they are registered on Form U4, F6).

**What the SEC IAPD bulk archive the platform ingests actually contains.** `fetch-adv-bulk` polls
`reports_metadata.json` (`adv_bulk_fetch.py:151`) and downloads
`https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/{year}/{file_name}` (`:173`) for
`ADV_Filing_Data_YYYYMMDD_YYYYMMDD.zip` (`:26`). The August 2026 archive was downloaded and listed:
100 CSV members. The parser selects four by regex — `(?:IA_ADV_Base_A|ERA_ADV_Base)_`,
`(?:IA|ERA)_Schedule_D_7B1_`, `..._7B2_`, `ADV_Filing_Types_` (`adv_bulk_ingest.py:126-129`) — and
from base rows reads only `FilingID`, `1E1`, `1A`/`1B1`, `1D`, `DateSubmitted`, `7B` (`:146-157`).
Members present in the archive and **never read**:

| Member | Header | Rows (Aug 2026) |
|---|---|---|
| `IA_Schedule_A_B` / `ERA_Schedule_A_B` | `FilingID, SchA-3, Schedule, Full Legal Name, DE/FE/I, Entity in Which, Title or Status, Status Acquired, Ownership Code, Control Person, PR, OwnerID` | 16,139 / 1,235; `DE/FE/I` = I 11,126, DE 4,092, FE 921 |
| `IA_ADV_Base_B` (and `ERA_ADV_Base`) | Item 2 columns **and `3A`** (organization form) | 3A: LLC 1,696, Corporation 488, LP 128, Other 41, LLP 20, **Sole Proprietorship 8**, Partnership 5 |
| `IA_1D3_CIK` | `FilingID, CIK` | 676 rows; 33 filings list more than one CIK |
| `IA_1E2_Additional_CRD` | `FilingID, CRDNumber` | 10 |
| `IA_SCH_R_CIK_1H`, `IA_Schedule_D_7A_CIK` | relying-adviser / Section 7.A CIKs | 190 / 1,141 |

`IA_ADV_Base_A` itself carries `1N` and `1N-CIK` (public-reporting-company CIK; 1 row `1N=Y`, 0 with
a CIK) but the parser does not read them. Item 3.A lives in `Base_B`, the member the code's own
comment deliberately excludes because it "carries only Item 2 fields and has no CRD column at all"
(`adv_bulk_ingest.py:118-125`) — accurate about CRD, but `3A` is there. Part 2B is *not* in this
archive: brochures ship separately as `ADV_Brochures_*.zip` (metadata index), so research 14 F7's
Part 2B gap stands; its "whether the archive includes Schedule A/B" open item is now closed: it
does.

**The published Schedule A/B has no `CRD No.` column.** The paper form's "CRD No. If None: S.S. No.
and Date of Birth …" column is absent from the CSV; in its place is `OwnerID` (7 digits; 11,182
non-blank of 16,139, 7,124 distinct, 1,611 values spanning more than one `FilingID`). No SEC page
reached defines `OwnerID`. Observation, not documentation: four `OwnerID` values were probed against
`https://api.adviserinfo.sec.gov/search/individual/<id>`; two returned an IAPD individual record
whose `individualId` equalled the `OwnerID` and whose name matched the CSV row (5637288 → "NANCY M
WESTBROCK" for row "WESTBROCK, NANCY, M"; 2246558 → "AARON SKLOFF" for "SKLOFF, AARON", with
`iaScope: Active`), two returned zero hits (3197325, 8304244). That is consistent with `OwnerID`
being the individual's CRD/IAPD id for individuals who are or were registered, but it is not
established by any published definition, and the SEC IARD page states Form ADV is published "except
for social security numbers, certain home addresses, and contact employee information" — the SSN/DOB
fallback in the paper column is exactly what a surrogate would suppress.

**Silver has no place for any of this.** `sec_adv_filing` = `accession_number, cik, form,
adviser_name, sec_file_number, crd_number, …` (`silver_schema.py:48-62`); no organization-form,
owner, or person column exists in any `sec_adv_*` table (`:38-109`). Research 14 F4 found the Person
hop unreachable because Path A writes `"cik": None` (`adv_bulk_ingest.py:237`); the firm's CIKs are
published in `IA_1D3_CIK` in the same ZIP.

### F3 — Cross-references between the two systems (Q3)

**Form ADV carries the firm's SEC file number, CIK(s) and CRD number(s) side by side.** Item 1.D:
"(1) If you are registered with the SEC as an investment adviser, your SEC file number: 801-____.
(2) If you report to the SEC as an exempt reporting adviser, your SEC file number: 802-____. (3) If
you have one or more Central Index Key numbers assigned by the SEC ("CIK Numbers"), all of your CIK
numbers: ____." Item 1.E: "(1) If you have a number ("CRD Number") assigned by the FINRA's CRD
system or by the IARD system, your CRD number: ____. (2) If you have additional CRD Numbers, your
additional CRD numbers: ____." Then the fence: "If your firm does not have a CRD number, skip this
Item 1.E. Do not provide the CRD number of one of your officers, employees, or affiliates." So a
CIK↔CRD crosswalk exists and is SEC-published — `IA_1D3_CIK` + `1E1` in the bulk archive — but it is
**firm-level only**. The platform reads `1D` (file number) and `1E1` (CRD) and discards `1D3`.

**Forms 3/4/5 carry no CRD.** EDGAR Ownership XML Technical Specification v5.1 (Sept 2015):
`reportingOwner` (max occur 10) → `reportingOwnerId` → `rptOwnerCik` (string, 10, **m**andatory for
submission types 3, 3/A, 4, 4/A, 5, 5/A), `rptOwnerCcc` (o), `rptOwnerName` (NA);
`reportingOwnerAddress` and `reportingOwnerRelationship` (`isDirector`, `isOfficer`,
`isTenPercentOwner`, `isOther`, `officerTitle`, `otherText`). "EDGAR verifies that each Reporting
Owner Central Index Key (CIK)/CIK Confirmation Code (CCC) pair is valid." A case-insensitive grep
for `crd` over all seven schema files returns nothing, and Appendix E (acronyms) lists
CIK/CCC/EDGAR/PDF/SEC/XML only. A 5.4 draft exists (page 404'd) and was not verified. edgartools
mirrors this: `Owner` has `cik, is_company, name, name_unreversed, address, is_director, is_officer,
is_other, is_ten_pct_owner, officer_title` (`ownershipforms.py:932-942`), parsed from
`rptOwnerCik`/`rptOwnerName` (`:1013-1014`); zero `crd` hits in `edgar/ownership/`. The repo parser
keeps `owner_cik`, `owner_name`, four flags and `officer_title` (`ownership.py:24-39`) and drops
edgartools' `is_company`.

**No individual-level CIK↔CRD crosswalk was found** on any SEC or FINRA page reached, and Form ADV's
Item 1.E fence forbids putting an individual's CRD in the firm's identifier block. For a natural
person the only join between an EDGAR CIK and a CRD record is name plus context (address on Form 4
vs. firm/office on IAPD).

### F4 — Uniqueness semantics (Q4)

**CIK.** The SEC defines it per filer account, permanent and unchangeable (F1), but not
one-per-natural-person: Item 1.D(3) asks for "all of your CIK numbers", and 33 of the 676
`IA_1D3_CIK` rows' filings list more than one CIK. That is firm evidence; for natural persons the
SEC pages reached neither assert nor deny that a person can hold several accounts (e.g. a trust in
the person's name filing under its own CIK is a separate filer account by the SEC's own definition).
edgartools' `is_company`/`is_individual` is a 9-signal heuristic over the SEC submissions record
("Uses a priority-based signal system with 9 checks", `entity/data.py:482-513`), i.e. the SEC
publishes no authoritative person/company flag per CIK.

**CRD.** BrokerCheck glossary: "A unique number assigned to investment professionals and brokerage
firms" — unique per record, and firms can hold more than one (Item 1.E(2); `IA_1E2_Additional_CRD`,
10 rows). Form U4 instructions: "Individual CRD Number. Provide the individual's CRD number that was
generated by the CRD system for the individual. If the individual's CRD number has not been
generated or is not known, leave this item blank." — the individual's number is looked up, not
re-minted, on each U4, which is the form used for "Registration or Transfer". That is the closest
primary statement to "one CRD per person across firms"; no FINRA page reached states persistence or
retirement explicitly ("Could not be determined"). The probe in F2 (one `individualId` carrying both
`bcScope` and `iaScope`) is consistent with one number per individual across broker and IA
registrations but is an observation, not a definition.

### F5 — Options for a Person key, stated factually (Q5)

What the platform's data can supply today, per option (ticket 02 decides):

1. **One merged surrogate** (a single Person id minted from whichever identifier arrives first, CIK
   or CRD, then unified). Requires an individual-level CIK↔CRD link. No SEC/FINRA source publishes
   one (F3); Forms 3/4/5 carry only `rptOwnerCik`; the ADV bulk path carries only firm identifiers
   plus Schedule A/B owner names and `OwnerID` (undefined by any reached document, F2). A merge
   would therefore rest on name+context matching, which research 11 F9 shows is a JW ≥ 0.80 unscoped
   match with no operative context today.
2. **Two typed identifiers on one identity, with a uniqueness invariant per type** (a Person may
   carry ≤1 CIK and ≤1 CRD; each value binds at most one Person). Supplies: `owner_cik` from every
   Form 3/4/5 owner row (`ownership.py:29`), and — only after new capture — the Schedule A/B
   `OwnerID` (if adopted as the CRD-type value) or nothing, since the CSV has no `CRD No.` column.
   The per-type "≤1 CIK per person" invariant is not guaranteed by the SEC (F4); the "≤1 Person per
   CIK" direction is what `mdm_person.owner_cik` lacks today (research 11: nullable, not unique).
3. **CRD as an Adviser-profile attribute only** (Person keyed by CIK; CRD stays on the firm
   registration profile, as `f"crd:{crd}"` does now, `adv_bulk.py:203-207`). Supplies everything the
   scheduled path already writes (`crd_number`, `sec_file_number`, no `cik`); reaches a Person only
   via the CIK-equality join research 14 F4 shows is dead on Path A, which `IA_1D3_CIK` could feed
   at firm level. Individuals from Schedule A/B would then be Person *assertions with a role toward
   the Adviser* (Clean MDM's "same-identity profile membership" language, research 14 F6), keyed by
   whatever identifier the capture chooses.

Under any option, a sole-proprietor RIA is two records in the source: a *firm* (Item 3.A "Sole
Proprietorship", firm CRD `1E1`, file number `801-…`, CIK(s) in `1D3`) and an *individual* Schedule
A row (`DE/FE/I = I`, "SOLE PROPRIETOR" title, `OwnerID`) — the Form ADV glossary classifies the
former as a company, and the two numbers differ (F1).

### F6 — IAPD vs IARD vs CRD vs BrokerCheck, and the SEC file number

1. **What each is.** *CRD*: "The CRD system is the central licensing and registration system used by
   the U.S. securities industry and its regulators. In general, information in the CRD system is
   obtained through the uniform registration forms that firms and regulatory authorities complete"
   (34-88760, p.4); FINRA operates it (footnote 7). *IARD*: "the Investment Adviser Registration
   Depository ("IARD"), an electronic filing system sponsored by the SEC and NASAA that collects and
   maintains the registration, reporting and disclosure information for investment advisers and
   related persons" (34-88760); "FINRA is the developer and operator of IARD" (iard.com); Form ADV
   must be filed "electronically through the IARD system. See SEC rules 203-1 and 204-4" (General
   Instruction 8). *IAPD*: "IAPD provides information about both SEC-registered and state-registered
   investment adviser firms, certain investment adviser firms that are exempt from registration with
   the SEC or states, and state-registered investment adviser representatives. The information in
   IAPD is derived from the Investment Adviser Registration Depository" (34-88760). *BrokerCheck*:
   "Information about investment professionals and brokerage firms made available through FINRA
   BrokerCheck is derived from the Central Registration Depository (CRD)" (BrokerCheck FAQ);
   "Through its BrokerCheck service, FINRA also provides basic information about investment adviser
   representatives and firms from the Securities and Exchange Commission's Investment Adviser Public
   Disclosure (IAPD) database."

2. **One number space.** Form ADV Item 1.E asks for the one "number ("CRD Number") assigned by the
   FINRA's CRD system or by the IARD system" — a single field, no separate "IARD number". General
   Instruction 9: a CRD account "will also serve as your IARD account; a separate account will not
   be established." For individuals, Form U4 is "the Uniform Application for Securities Industry
   Registration or Transfer. Representatives of broker-dealers, investment advisers, or issuers of
   securities must use this form … These instructions apply to the filing of Form U4 electronically
   with the Central Registration Depository ("CRD®") or the Investment Adviser Registration
   Depository ("IARD℠)", and its identifier field is "Individual CRD Number". 34-88760 footnote 12:
   "With respect to investment adviser representatives, IARD provides for the filing of these Forms
   through the CRD system." No source uses "IARD number" as a distinct identifier.

3. **Source of individual (IAR) records on IAPD.** Form U4/U5/U6 filed "with the CRD system"
   (34-88760: "both systems display information about individuals that has been filed with the CRD
   system on Forms U4, U5 and U6"); IAPD "had previously only included information on investment
   adviser firms" until the SEC expanded it "to include information on investment adviser
   representatives" (FINRA RN 12-10). **The bulk download the platform ingests is firms only**: the
   SEC FOIA page describes "Form ADV Part 1 and Form ADV-W Data Files for SEC registered investment
   advisers and for SEC exempt reporting advisers"; `reports_metadata.json` lists exactly five
   families (`ADV_Filing_Data_*`, `ADVW_*`, `ADV_Brochures_*`, `FIRM_CRS_MONTHLY_*`,
   `FIRM_CRS_DOCS_MONTHLY_*`) with zero individual-level files; the 100-member archive has no U4/IAR
   table. Natural persons appear only as Schedule A/B owner/officer rows and DRP affiliate rows of a
   *firm* filing (F2). Individual IAPD records exist per-CRD
   (`reports/individual/individual_<crd>.pdf` returned S3 AccessDenied; the search endpoint
   answered, F2) — not as a bulk dataset on any page reached.

4. **Dual registrants.** 34-88760: "information on many registered individuals can be obtained in
   either system because the majority of brokers are also registered as investment adviser
   representatives and vice versa", and footnote 13 refers to "the minority of individuals who are
   not dually registered". Together with (2) — one Form U4, one "Individual CRD Number", filed to
   CRD whether via CRD or IARD — the primary text supports one CRD number per individual across both
   capacities; no sentence states it outright.

5. **The SEC file number is a third, SEC-side registration identifier for the firm.** Item
   1.D(1)/(2): "801-" for registered advisers, "802-" for exempt reporting advisers; the
   paper-filing header rule requires "your SEC 801-number (if you have one), or your 802-number (if
   you have one), and your CRD number (if you have one) on every page" — three identifiers on one
   filing (with CIK(s) in 1.D(3)). It is assigned to firms only, never to individuals, and the
   platform already stores it (`sec_file_number`, `adv_bulk_ingest.py:155`; `silver_schema.py:53`).

## What this settles for ticket 02 Q2

- CIK identifies an EDGAR filer account (company, fund or natural person); CRD identifies a
  FINRA/IARD registration record (firm or individual, distinct numbers even for a sole proprietor).
  Neither issuer references the other for individuals; no individual-level crosswalk is published
  (F1, F3).
- The Form 3/4/5 identifier is exactly `rptOwnerCik`, mandatory, no CRD element (F3). The scheduled
  ADV path's identifiers are all firm-level: CRD (`1E1`), file number (`1D`), and — present in the
  archive but unread — CIK(s) (`IA_1D3_CIK`) and additional CRDs (F2, F3).
- Natural persons on the ADV side exist today only as unread `Schedule_A_B` rows: name, `DE/FE/I`,
  title, ownership code, control flag, and an `OwnerID` with no published definition; the paper
  form's "CRD No." column is not in the CSV (F2). IARs are not in the bulk download at all (F6.3).
- Neither identifier is one-per-natural-person by the issuer's own rules: Form ADV collects "all of
  your CIK numbers" and "additional CRD Numbers"; the SEC publishes no per-CIK person flag (F4).
  "One CRD per individual across firms" is supported by the U4 instruction wording and the
  dual-registration statements, not by an explicit sentence (F4, F6.4).
- A CRD number can therefore bind a Person only if the platform adopts the ADV Schedule A/B
  `OwnerID` (or an individual IAPD id obtained some other way) as that value; nothing the platform
  currently writes to silver can (F2, F5).

## Could not be determined

- Whether `OwnerID` in `IA_Schedule_A_B` *is* the individual CRD number: no SEC data dictionary was
  found; 2 of 4 probes matched an IAPD `individualId` by number and name, 2 returned nothing.
- Whether an individual's CRD number is ever retired, reused, or reassigned, and an explicit
  FINRA/SEC sentence that it persists across firms — the reached primary pages define the number but
  are silent on persistence.
- Whether a natural person can hold more than one CIK: the SEC defines the CIK per filer account and
  never says one-per-person; multi-CIK evidence here is firm-level only.
- Whether the SEC/FINRA publish any individual-level (IAR/U4) bulk dataset: none appears in the FOIA
  index or on the pages reached; individual reports were only observable per-id.
- What the Ownership XML spec 5.4 draft changes (page 404'd); v5.1 was verified.
- Which of the 100 archive members beyond Base_A/B, 7B1/7B2, Filing_Types, Schedule_A_B, 1D3_CIK,
  1E2_Additional_CRD carry person-shaped data (DRP members were listed, not opened).
