# 174: sec.prospectus: the final prospectuses (424B1 to 424B5), looked up on MDM, then landed in silver

Priority: 174. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 17:33 ET (operator, 2026-11-02: "Have a ticket to capture this", "Look-up on mdm then silver").

Type: task. Status: open, not started. Blocked by: the operator's permission for the SEC requests (below). Related: [149](149-s1-registration-statements.md) (`sec.registration`, the S-1 and F-1 originals; the name stays, 2026-11-02: "Agreed").

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

- [ ] The operator's permission for the SEC requests of this feed, with the forms and the scope (nothing is requested before it)
- [ ] Count the 424B1, 424B2 and 424B5 filings from the captured submissions (no request), and the size of their main documents
- [ ] Decide with the operator which forms and which facts: the offer terms (price, shares, underwriters, exchange), or the document kept unread first, as for `sec.registration`
- [ ] Outside standards first (the research skill): how a 424B prospectus is structured and which parts are tagged
- [ ] Capture: a source `sec.prospectus` with its `acquisition` feed, a Bookkeeping capture target and the Change Journal, shaped like `sec.registration`
- [ ] The look-up: each filing's filer found in MDM by CIK; a filer MDM does not hold is set aside with its reason, never created here
- [ ] The silver table (the Silver Spec, its grain and key, the link to the Company), landed through the `silver.land` step, with its first quality checks (the operator decides the checks)
- [ ] A limited proof only: a few invented documents, a second pass that changes nothing, an unchanged file skipped
- [ ] The Mapping Document and the Data Catalog entry are regenerated; tests that pin the source order are run before the first push
- [ ] Stores and containers a test run leaves are removed
- [ ] Learning → skill: the `data-onboarding` and `company-financials` skills name this feed and its look-up, or "none"
