# 174: sec.prospectus: the final prospectuses (424B1 to 424B5), looked up on MDM, then landed in silver

Priority: 174. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 17:33 ET (operator, 2026-11-02: "Have a ticket to capture this", "Look-up on mdm then silver").

Type: task. Status: open (operator, 2026-11-17: "Implement ticket 149 and 174 using SpaceX as the test case"). Blocked by: none. Related: [149](149-s1-registration-statements.md) (`sec.registration`, the S-1 and F-1 originals; the name stays, 2026-11-02: "Agreed").

## Question

`sec.registration` captures the registration statement a company files before an offer. The SEC also has the **final prospectus**, forms 424B1 to 424B5, which a company files after the offer is priced: it states the final price, the number of shares and the underwriters. A source called `sec.prospectus` holds these forms, and only these. What does it take to capture them, look each filer up in MDM, and land them in silver?

## What the operator ruled (2026-11-02)

- The name `sec.prospectus` is for the 424B forms; `sec.registration` keeps the S-1 and F-1 originals.
- **Look up on MDM, then silver:** the filer is found in MDM by its identifier (the Company holding the CIK), and the document's facts are landed in silver linked to it. MDM is not written: a prospectus is not a master record, and no master field is copied (the rule of [149](149-s1-registration-statements.md), "Where the results go").

## Facts already known (no request)

- Ticket 149 counted, from the captured submissions, 424B3 in 53,659 filings and 424B4 in 4,598. The counts of 424B1, 424B2 and 424B5 are to be found the same way.
- A 424B4 follows the pricing of an IPO; a 424B3 is most often a resale or a supplement. Which of the five forms carry the offer terms is to be decided with the operator.
- The feed needs the same capture as `sec.registration` (`provider.capture`, `sec.conditional`, the main document only, the 128 MiB ceiling).

## Parts

- [ ] ~~The operator's permission for the SEC requests of this feed, with the forms and the scope (nothing is requested before it)~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~Count the 424B1, 424B2 and 424B5 filings from the captured submissions (no request), and the size of their main documents~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~Decide with the operator which forms and which facts: the offer terms (price, shares, underwriters, exchange), or the document kept unread first, as for `sec.registration`~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~Outside standards first (the research skill): how a 424B prospectus is structured and which parts are tagged~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~Capture: a source `sec.prospectus` with its `acquisition` feed, a Bookkeeping capture target and the Change Journal, shaped like `sec.registration`~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~The look-up: each filing's filer found in MDM by CIK; a filer MDM does not hold is set aside with its reason, never created here~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~The silver table (the Silver Spec, its grain and key, the link to the Company), landed through the `silver.land` step, with its first quality checks (the operator decides the checks)~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~A limited proof only: a few invented documents, a second pass that changes nothing, an unchanged file skipped~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~The Mapping Document and the Data Catalog entry are regenerated; tests that pin the source order are run before the first push~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~Stores and containers a test run leaves are removed~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").
- [ ] ~~Learning → skill: the `data-onboarding` and `company-financials` skills name this feed and its look-up, or "none"~~ deferred to 212: the operator closed all tickets (2026-11-11 15:02 ET: "Close all tickets consolidate remaining issues into new ticket by priority and go-live").

## Reopened 2026-11-17 (operator: "Implement ticket 149 and 174 using SpaceX as the test case")

Rulings, one question each (operator, 2026-11-17 10:43 ET):

- SEC requests: "SpaceX 424B4 only (Recommended)": one request, the main document of the issuer's 424B4 (filed 2026-06-12), through the configured capture with its receipt. Nothing wider without a later word.
- Forms and facts: "424B1 to 424B5, cover terms": the source names all five forms; each row holds the cover's final price per share, shares offered, over-allotment shares, underwriting discount, proceeds to the company, ticker, exchange and the lead underwriters, each empty when the cover does not state it.
- Committed tests and rules use invented pages; the SpaceX proof runs on a disposable store and is reported in counts.

Parts:

- [ ] The source `sec.prospectus`: its acquisition feed (424B1 to 424B5, the SEC archive prefix, `sec.conditional`, `text` completeness), its capture target and its silver target, shaped like `sec.registration`; `rules check` passes
- [ ] The units: from the captured submissions, every 424B1 to 424B5 filing listed (counts only in this file); the request written for the one permitted filing
- [ ] The capture: the one permitted request through `provider.capture`, its receipt, journal event and verifier
- [ ] Profile the captured page: which cover terms it states, and where
- [ ] The reading (`prospectus-page.yaml`): the cover terms by the engine's text operations, configuration only; a test on an invented page
- [ ] The silver table `prospectus_offering` (grain one row a filing, key accession), linked to the Company by CIK and to the Security by ticker (ticket 149's link)
- [ ] The Mapping Document and catalog regenerated; the tests that pin the source list run
- [ ] The proof on a disposable store: the test case lands one row with its terms, linked to its Company; a second pass changes nothing
- [ ] Stores and containers the proof leaves are removed
- [ ] Learning → skill

