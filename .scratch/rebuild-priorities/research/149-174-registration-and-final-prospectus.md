# Registration statements (S-1) and final prospectuses (424B): what they state, and what is tagged

Research for tickets 149 (the S-1 and F-1 originals, `sec.registration`) and 174 (the final prospectuses,
`sec.prospectus`). Primary sources only; each finding is checked against the pages captured on this machine
(counts only). Read 2026-11-17.

## Sources

| Source | What it settles |
|---|---|
| Form S-1 and its General Instructions (SEC, form revision "SEC 870 (07-24)", OMB 3235-0065), `https://www.sec.gov/files/forms-1.pdf` | The items an S-1 holds and where each points in Regulation S-K |
| Regulation S-K Item 501, 17 CFR 229.501 (Cornell LII, `https://www.law.cornell.edu/cfr/text/17/229.501`) | What the outside front cover of every prospectus must state |
| Regulation S-K Item 601(b)(101) and (b)(107), 17 CFR 229.601 (Cornell LII) | When financial statements must be tagged; the filing fee table exhibit |
| Regulation S-T Rule 405, 17 CFR 232.405 (Cornell LII) | The tagged file is Inline XBRL |
| Rule 424, 17 CFR 230.424 (Cornell LII) | What each 424B paragraph files, and when |
| Data-vendor IPO calendars (OpenBB's `CalendarIpo` model, Nasdaq's IPO calendar page) | How others model an IPO pipeline |

eCFR refused an automated reader, so the CFR text was read from Cornell LII, which republishes it.

## What an S-1 holds

Part I of Form S-1 is the prospectus. Each item points to a Regulation S-K item:

- Item 1, the forepart and the outside front cover: S-K Item 501.
- Item 4, use of proceeds: Item 504.
- Item 5, determination of offering price: Item 505.
- Item 6, dilution: Item 506. A SPAC is exempt.
- Item 7, selling security holders: Item 507.
- Item 8, plan of distribution: Item 508.
- Item 9, the securities registered: Item 202.
- Item 11, the registrant. It covers business, MD&A, market risk, directors, pay, ownership and related parties. Item 11(e) asks for "financial statements meeting the requirements of Regulation S-X".

Part II Item 16(c) asks for the "Calculation of Filing Fee Tables" in the tabular form of S-K Item 601(b)(107), filed as an exhibit under Regulation S-T Rule 408.

**Checked against the capture.** Ticket 149 measured that the registration fee table appears in the main document in 845 of 860 filings from 2001 to 2021. It appears in 193 of 384 from 2022 to 2026, the years after Item 601(b)(107) made the fee table its own exhibit. That move explains the drop. The main document cannot be the source of the aggregate offering price for recent filings, and `registration_offering` leaves it empty, as ruled.

## What every prospectus cover states (S-K Item 501(b))

The cover is limited to one page and must state:

- the registrant's name;
- the title and amount of securities, separately for selling security holders, and the over-allotment option with "the amount of additional shares that the underwriter may purchase";
- for a cash offering, "the price to the public of the securities, the underwriter's discounts and commissions, the net proceeds you receive", "on both a per share or unit basis and for the total amount of the offering", "in a table, term sheet format, or other clear presentation";
- in a preliminary prospectus of a non-reporting issuer, a bona fide estimate of the price range and the maximum number of securities. For debt, it is the principal amount instead;
- "the national securities exchange(s) where the securities being offered are listed" and "the corresponding trading symbol(s)";
- the lead or managing underwriters and the nature of the underwriting arrangement;
- the prospectus date;
- before effectiveness or pricing, the "Subject to Completion" legend.

**What this means for the readings:**

- The cover terms are a closed list set by Item 501, which is why one reading serves the S-1 and every 424B. The price, the discount and the proceeds always come per unit and in total. The form of their table is free, and pages lay it out in two ways: a row per line, or a column per line.
- A preliminary prospectus may give a range, or nothing. An S-1 gives the range (`price_low`, `price_high`), and a final prospectus gives the price. A page carrying the completion legend, with blank amounts, has nothing to land, and that is correct.
- The trading symbol named on the cover is the issuer's own listing. A structured note's cover and terms also name the symbols of what it is linked to, so a reading must take the symbol from the issuer's listing sentence only.

## What each 424B is (Rule 424(b))

| Form | Files | Due |
|---|---|---|
| 424B1 | Information left out of the effective registration statement under Rule 430A (the price of an offering priced at effectiveness) | Second business day after pricing or first use |
| 424B2 | A primary shelf or delayed offering under Rule 415(a)(1)(x), (vii) or (viii): information left out under Rule 430B (or 430D, asset-backed) | Second business day after pricing or first use |
| 424B3 | Facts or events that substantively change the last filed prospectus, other than (b)(1), (b)(2) or (b)(6) | Fifth business day after first use |
| 424B4 | Both (b)(1) and (b)(3) information: the usual final IPO prospectus | Second business day after pricing or first use |
| 424B5 | Both (b)(2) and (b)(3) information: a priced shelf takedown | Second business day after pricing or first use |

Rule 424(b)(7) (selling holders) and (b)(8) (a late filing) exist too. The feed does not list them.

**Checked against the capture.** In the captured submissions from 2026, 424B2 is 62,836 filings, 424B5 1,759, 424B3 4,012, 424B4 328 and 424B1 12. The rule explains the mix:

- 424B2 is a shelf issuer's pricing supplement. Both sampled ones are bank structured notes, with no shares and no ticker, and their price table is turned. The 424B5 sample has one equity takedown and one note.
- 424B3 is any change to a prospectus: one sample is a resale of shares with no price, the other a preliminary note supplement.
- 424B1 is a price added at effectiveness: one sample is preferred shares, the other an asset-backed bond priced by tranche.

The share terms (shares, price per share, over-allotment, ticker) belong to equity covers only. The price lines (offering price, discount and proceeds, per unit and in total) belong to every cash offering.

## What is tagged

- Financial statements in a Securities Act registration statement need an Interactive Data File "only if the registration statement contains a price or price range" (S-K Item 601(b)(101)(i)(B)), in Inline XBRL (S-T Rule 405(a)(3)). The file is an exhibit of the filing. It is not in the main document this feed captures, and nothing in the main document is tagged.
- The cover page Interactive Data File (Item 601(b)(104), S-T Rule 406) applies to the forms Rule 406 names. The cover terms on the page above are text, and are read by their words.
- The filing fee table has been its own exhibit since Item 601(b)(107), and it is structured there.

**So:** reading the main document by its words is the only way to get the cover terms from the files captured. A tagged reading would need the exhibits, which means new SEC requests and their own ruling: the Inline XBRL financial statements of a priced S-1, and the fee table exhibit.

## How others model an IPO pipeline

The vendor calendars use a few stages: filed, expected or upcoming (scheduled, not yet priced), priced, and withdrawn. They carry dates for filing, expected pricing and withdrawal (OpenBB `CalendarIpo`: `filed_date`, `expected_price_date`, `withdraw_date`). Nasdaq says its expected dates are estimates from company filings, not official.

The filings themselves give the same stages without an estimate:

- filed: the S-1 or F-1, and before it the confidential draft (DRS);
- effective: the `EFFECT` notice;
- priced: the 424B4, or a 424B1;
- withdrawn: an RW filing, which is not captured today.

Each stage is a filing date in the captured submissions, so no vendor calendar is needed. Ticket 149 counted, from the captured submissions, 32,473 `EFFECT` notices and 4,598 424B4 filings.

## Limits found

- The asset-backed bond sample prices each tranche in percent, in a table with a column per term. Neither the row reading nor the turned reading takes it, so its price lines are empty.
- A preliminary note supplement states its price lines as blanks or "% of the face amount". Nothing lands until its final supplement.
- A note priced in percent of face would land the percent's number as the amount. The rows record no unit, and none of the eight samples did this.
