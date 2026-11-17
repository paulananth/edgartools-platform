# 174: sec.prospectus: the final prospectuses (424B1 to 424B5), looked up on MDM, then landed in silver

Priority: 174. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 17:33 ET (operator, 2026-11-02: "Have a ticket to capture this", "Look-up on mdm then silver").

Type: task. Status: resolved (operator, 2026-11-17: "Implement ticket 149 and 174 using [the test issuer] as the test case"). Blocked by: none. Related: [149](149-s1-registration-statements.md) (`sec.registration`, the S-1 and F-1 originals; the name stays, 2026-11-02: "Agreed").

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

## Reopened 2026-11-17 (operator: "Implement ticket 149 and 174 using [the test issuer] as the test case")

Rulings, one question each (operator, 2026-11-17 10:43 ET):

- SEC requests: "[the test issuer] 424B4 only (Recommended)": one request, the main document of the issuer's 2026 424B4, through the configured capture with its receipt. Nothing wider without a later word.
- Forms and facts: "424B1 to 424B5, cover terms": the source names all five forms; each row holds the cover's final price per share, shares offered, over-allotment shares, underwriting discount, proceeds to the company, ticker, exchange and the lead underwriters, each empty when the cover does not state it.
- Committed tests and rules use invented pages; the test issuer's proof runs on a disposable store and is reported in counts.

- A third, from the proof (operator, 2026-11-17 11:18 ET): "Master the 86 (Recommended)". SEC types a just-listed company "other" until its first annual report, so the Company rule set the test issuer aside and its rows had no Company. The rule's new step `10a` masters a filer typed "other" with a ticker that filed an S-1, F-1, S-11, 424B1 or 424B4 (version `2026-11-17.listed-operating-foreign-or-new-listing`). Counted over the captured submissions (76,230 filers): 86 such filers name an exchange, 89 more hold a ticker with no exchange in their submissions file; the rule reads the ticker, as its other steps do, so it masters both (175). 554 listed filers typed "other" with none of those forms stay set aside.

Parts:

- [x] 2026-11-17 11:18 ET The source `sec.prospectus`: its acquisition feed (424B1 to 424B5, the SEC archive prefix, `sec.conditional`, `text` completeness), its capture target and its silver target; `rules check` passes
- [x] 2026-11-17 11:18 ET The units (`.scratch/onboarding/sec.prospectus/units.py`, local files only): the captured submissions list 424B1 761 filings (12 from 2026), 424B2 129,714 (62,836), 424B3 48,459 (4,012), 424B4 4,587 (328), 424B5 30,847 (1,759); one request written, for the permitted filing
- [x] 2026-11-17 11:18 ET The capture: one SEC request through `provider.capture` by the unit (a provider capture holds the shared `provider:sec` lease, so it does not run at grain `run`; the shape now refuses it there, `test_a_provider_capture_runs_by_the_unit_holding_the_providers_lease`); 1 unit verified, the run complete with `journal.delivered`; one page of 11.9 MB in `sec.prospectus/first-424b4`, with its receipt
- [x] 2026-11-17 11:18 ET Profile of the captured page: the cover text states shares, price per share, ticker and exchange (the page's lines are text blocks); the per-share and total amounts sit in a cover table, repeated in the underwriting section; the underwriters and their shares sit in the underwriting table ("Name | Number of Shares"), the cover lists the firms only
- [x] 2026-11-17 11:18 ET The reading (`prospectus-page.yaml`, configuration only): `offering` from the cover text, `cover_line` (offering price, underwriting discount, proceeds: per share and total) and `underwriter` (each firm and its shares) from the rows; `tests/engine/test_prospectus_page_reading.py` on an invented page (4 tests)
- [x] 2026-11-17 11:18 ET Three silver tables: `prospectus_offering` (one row a filing, linked to the Company by CIK and to the Security by ticker), `prospectus_cover_line` and `prospectus_underwriter` (one row a page row, linked to the Company); the lead underwriters are the underwriting table's rows, not a cover column
- [x] 2026-11-17 11:18 ET Mapping Documents regenerated (`sec.prospectus`, `sec.registration`, `sec.company`, the company kind; `rules mapdoc check` clean); `sec.prospectus` in the source sequence, the load chain (`sec.prospectus/first-424b4`) and the tests that pin the source list
- [x] 2026-11-17 11:18 ET The proof on disposable store `t174`: the Company loaded from a one-filer slice of the submissions capture (mastered by step `10a`); the 424B4 landed 1 offering row (shares, price, over-allotment shares, ticker and exchange all stated), 6 price lines (the cover table and the underwriting section's, equal) and 22 underwriters whose shares sum to the shares offered; every row linked to the Company; the Security link empty (no Security holds the ticker). A second pass of both silver loads: "0 documents loaded, 1 already loaded before", every row unchanged
- [x] 2026-11-17 11:18 ET Stores and containers the proof leaves are removed: `local-test-stores.py stop t174`; the two one-filer capture slices (hard links) stay beside their captures for the hosted run
- [x] 2026-11-17 11:18 ET Learning → skill: `bookkeeping` "Write `grain: run` on every target but a provider capture" and "Run a provider capture by the unit"; `data-platform` READING.md (a term in a table is read as its own `each: row` table; a `select` of two conditions); `data-onboarding` TARGETS.md (a row links by an identifier the master holds)
