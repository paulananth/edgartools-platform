# DTCC official-source discovery repeated October 9, 2026

Status: research and access evidence only. No registration, vendor contact, purchase, SEC request, source activation or mastering binding. This note rechecked live official pages rather than relying on the previous report.

The investigation followed the merged narration requirements in data-profiling
and data-onboarding at `4489170c`, explaining findings in the conversation as
they emerged. [Repeat evidence](../../.scratch/onboarding/dtcc-directories/repeat-20261009/qualification.json)
records the command, hashes and comparison with the prior profile.

## Discovery story

First I checked whether the previously identified directory sources still exist and whether public files were confused with member services. The directory pages continue to expose public downloads, but describe participants of clearing subsidiaries rather than an exhaustive Company registry. The next check separated actual publication labels from a promised refresh schedule: only NSCC states monthly workbook updates and weekly participant notices.

Then I followed the terms link. The web text extractor omitted the page's accordion content. Inspecting the live HTML exposed material restrictions previously missed by that extraction. This changes the next step: anonymous availability is demonstrated, but automated ingestion and database use need written rights evidence. The onboarding proposal cannot infer such permission from a free download link.

Finally I checked the retained lower-priority sources. Their own dates and access rules differ from the directory workbooks. They remain candidates for narrower enrichment rather than a full security or beneficial-owner universe.

## Directory evidence

| Source | Verified publication label | Refresh evidence | Access and meaning |
|---|---|---|---|
| [DTC directories](https://www.dtcc.com/support/dtc-directories) | September 30, 2026 | No cadence stated on this page | Page explicitly describes public free participant listings. Includes alphabetical/numerical participants, settling banks, pledgees and direct registration links. These are DTC participation records, not proof each row is an independently mastered Company. |
| [NSCC directories](https://www.dtcc.com/support/nscc-directories) | Member and MPID files: Updated 09/2026 | Explicit monthly Excel updates; participant-change notices weekly | Directory available to interested parties. Need notices to avoid treating the monthly snapshot as current on every intervening date. MPID directory requires account/market-role semantics before entity mapping. |
| [FICC GSD and CCIT](https://www.dtcc.com/support/ficc-gov-directories) | GSD October 8, 2026; CCIT February 25, 2025 | No cadence stated | Sponsored-member list moved to member-only MyDTCC February 10, 2025. Public GSD/CCIT coverage is consequently not a complete sponsored-member population. |
| [FICC MBSD](https://www.dtcc.com/support/ficc-mbs-directories) | September 25, 2026 | No cadence stated | Public participant directory link; clearing membership is the stated domain. A filename date alone does not establish effective-from or membership lifecycle. |

The current role distinctions matter for MDM: participant/account numbers and MPIDs are evidence of a source-specific membership or trading role. Connecting these to a Company requires independently reviewed namespaces, holder/cardinality and identity evidence. The official directory descriptions do not approve a CIK/LEI crosswalk or a new binding rule.

## Important notices and RSS

[DTCC's RSS documentation](https://www.dtcc.com/rss-feeds) says notices are available without subscription or password and describes RSS summaries, automatic updates and possible reader delays. This specifically establishes a supported feed-reader workflow; it does not settle directory redistribution rights.

The [all-important-notices XML](https://www.dtcc.com/rss-feeds/legal/all-important-notices.xml) was fetched anonymously and parsed successfully locally: 1,000 items. Titles can be notice codes, with substantive topics in descriptions. This is an observed current feed size, not a complete historical archive or demonstrated weekly membership-change coverage. A title-only membership filter would miss relevant topics; subject/content qualification is still needed.

For example, notice `25130-26` is published October 9, 2026, while its summary describes DRS changes planned for November 13, pending regulatory approval. Publication time and effective time are separate. [Official notice](https://files.dtcc.com/download/assets/25130-26/a9d42d58c3e511f1b02c76c53cdc9348).

## Rights discovery requiring resolution

[DTCC Terms of Use](https://www.dtcc.com/terms), updated March 11, 2026, provide a limited revocable licence. The live HTML's licence accordion restricts database/information-service compilation, copying and distribution except with written DTCC authorization. It also restricts automated mining or systematic extraction. Separate Agreements control conflicting terms. Another accordion preserves CGS/ABA proprietary rights to CUSIP material; public access transfers no proprietary rights.

**Discovery conclusion:** a free public page is insufficient evidence of authorization for planned automated ingestion, internal database compilation or redistribution. Obtain the applicable dataset agreement or written permission and resolve any identifier rights before automated onboarding. No such agreement was found in the directory pages checked. This is a source-rights finding, not legal advice. The permission contact is documented on the terms page; nobody was contacted.

Evidence limitation: the browsing text renderer showed only the terms introduction. Local HTML `/private/tmp/dtcc-terms-repeat.html` contains the relevant `AccordionHeader`/`AccordionPanel` fields and streamed page text. The finding depends on that full live source, not the abbreviated renderer.

## Retained lower-priority sources

### Selected CUSIP certification/restriction lists

[DTC reference-directory landing page](https://www.dtcc.com/support/dtc-reference-directory) says updated September 29, 2026, and links three public PDF lists. That date cannot be applied to every PDF:

- [Ownership-certification PDF](https://files.dtcc.com/download/assets/DTC-Securities-Subject-To-Ownership-Certifications.pdf/2cd7e22489cd11f1b68692cc7dabea24): four pages; explicitly updated July 17, 2026. Lists issuer descriptions, CUSIPs, SEG-100 and automatic-certification flags for selected foreign/specialized ownership restrictions. DTC disclaims accuracy of identifications. This is restricted-security reference evidence, not a complete Security Master or actual holder register.
- [Section 3(c)(7) PDF](https://files.dtcc.com/download/assets/Corporate-And-Municipal-Reference-Directory.pdf/feb75dba369511f0a787c204a2f8334f): 100 pages; explicitly updated September 21, 2026. Contains CUSIPs and security descriptions and explains issuer reliance on an investment-company-definition exemption. DTC disclaims accuracy. Preserve document date, legal notes and source context; do not turn absence from this selected list into a negative rule.
- [Limited partnership special-deposit PDF](https://files.dtcc.com/download/assets/Limited-Partnership.pdf/2ed99c7a89cd11f197bb6ead45669f61): three pages, selected issuer/security descriptions and CUSIPs; certification/deposit-process context and DTC accuracy disclaimer. No internal update date established by the extraction, so use retrieval time separately from the landing-page label.

PDF extraction and CUSIP permission remain unqualified. Retain as lower priority, as requested.

### Security Position Reports

[SPR official page](https://www.dtcc.com/products-and-services/asset-services/issuer-services/security-position-reports) limits the described users to issuers, trustees and approved third-party agents. Registered users request reports for their firm; reports cost money and may be requested individually or by subscription. Subscriptions require at least one year. Browser, spreadsheet and CCF delivery are described, with a dividend-record-date CCF exception.

The report identifies which DTC participants hold an issuer's security and contact details during a period. Participants communicate onward to customers. It therefore cannot be represented as a public full-market beneficial-owner feed. Eligibility, actual fees, security scope and authorized reuse remain unresolved for this platform.

### Security Master File Data

[Current dedicated product page](https://www.dtcc.com/products-and-services/data-services/corporate-actions-reference-data/security-master-file-data) describes reference data for over four million active DTCC-eligible securities and routes users to contact DTCC. It does not publish a price, open downloadable corpus, an automatic approval criterion or a registration entitlement that grants this dataset.

[Parent reference-data page](https://www.dtcc.com/products-and-services/data-services/corporate-actions-reference-data) places it among reference/corporate-action solutions; it supports enrichment of security records and trade processing. A live official-source search found no verified current subscription tariff. The platform would need a quote and applicable agreement before cost or usage approval; no quote was requested. Do not substitute unrelated NSCC mutual-fund Security Master fees or third-party licence prices.

## Local discovery: what the rows actually established

Ten anonymous recaptures returned HTTP 200 in 5.59 seconds. Each hash matches
the prior workbook: this is the same dated snapshot, not a second delivery for
testing key persistence. Downloads completed before the full licence clauses
were found; recurring acquisition is not approved by that access test.

The full profile of 14 exported regions and 13,870 rows completed in 21.2
seconds (9.2 seconds inside the profiler, excluding command startup). Every
part and all 22 questions match the prior findings exactly; fingerprints are
byte-identical. Nine classes remain unknown, one is suggested as reference and
four as master. Those suggestions remain unapproved, as do the designed keys.
The known report-label bug still emits `None`; output was retained unchanged.

Every exported cell was rechecked against its original worksheet region.
The raw XLSX probe still refuses the input with `found ['xlsx']`. Successful
export profiling consequently does not qualify original-format reading or a
production pipeline. Source row coordinates and grid hashes remain pinned.

| Check | Measured finding | Consequence for the proposed onboarding |
| --- | --- | --- |
| DTC numerical-sheet regions | 914 four-digit account rows, 73 series headings, 3 blank rows | 990 exported rows do not mean 990 participants. Headings and blanks need explicit audited record boundaries. |
| DTC alphabetical vs numerical | The same 914 account representations occur in both. Exact source-name equality is zero; equality after trimming is 914. | These are alternative presentations of the same account list. Whitespace comparison is diagnostic only; no normalization or Company match is approved. |
| NSCC `gustno` duplicate | Source rows 3000 and 3001 are identical across all 11 columns; key text is `22959` with trailing spaces. | Preserve duplicate provenance. A proposed account key needs an explicit duplicate policy; a surrogate proposal is not automatically the right answer. |
| Corporate MPID repetitions | `MZHO` at rows 898/899 and `NMRA` at 921/922 differ only in `CLEARING BROKER`. | An MPID alone does not identify the complete row. A last-row-wins rule would discard a broker relationship. |
| Guide to Symbols | A one-row documentary worksheet is included in the exploratory profile. | Its designed key and unknown class do not justify creating an entity dataset. Retain it as interpretation evidence pending review. |

These counts are reproduced in [local evidence](../../.scratch/onboarding/dtcc-directories/repeat-20261009/local-evidence.json).
The full prior [profile](../../.scratch/onboarding/dtcc-directories/profile/REPORT.md)
and [draft findings](../../.scratch/onboarding/dtcc-directories/profile/findings.yaml)
remain the review artifacts; repeat output hashes identify the new local files
without duplicating unchanged findings and fingerprints in Git. Fresh captures,
repeat profile and terms HTML are also retained under
`~/.local/share/edgartools/clean-mdm/research/dtcc-repeat-20261009/`.

The profile's 22 questions cover nine unknown classes, nine designed keys and
four proposed master kinds. Before asking the operator to accept surrogates or
new kinds, review the actual data boundaries and source roles: blank rows,
series headings and duplicate account observations explain several failed
uniqueness tests. No proposal is converted into a rule here. Company overlap
and account-to-Company cardinality are not measured by this directory profile.

## What remains unanswered

- Dataset-specific permission for automated recurring captures, internal MDM compilation and downstream distribution, including CUSIP rights.
- Complete participant/account/MPID semantic definitions and validity periods; public directory evidence alone cannot approve Company identity bindings.
- Original-format parser qualification and exact workbook/PDF record boundaries.
- Complete member-change notice coverage, relevant routing and publication/effective-date handling.
- Freshness expectations for DTC, CCIT, GSD and MBSD beyond their observed date labels.
- SPR eligibility, paid authorized scope and fees; Security Master quote, contract, schema and delivery.

Next justified action is to present these findings and the local profiles for operator review. Production rules, mapping, activation or new automatic acquisition remain behind the unresolved rights and semantic approvals.
