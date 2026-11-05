# sec.registration: profile and silver design for valuation and pricing

2026-11-04 18:17 ET. Counts only. Operator, 2026-11-04: "profile it and design the silver download from sec
if required"; the model is Damodaran's valuation tools (the operator's link: his valuation tools page).

## What the profile found (732 filings from 2026, all read, none refused)

- The reading gives 3 parts: `page` (732 rows, one per filing, key `accession`), `blocks` (1,259,259 text
  blocks, key `accession` + `seq`), `rows` (729,992 table rows, key `accession` + `seq`, cells `c1`..`c12`).
  Every block and row points at its page (inclusion 1.0).
- The profiler calls `page` a master. It is not: a registration is an event of a Company, and the Company is
  mastered from the SEC filer file. `page` becomes silver `registration_offering`; `rows` is not a
  relationship, it is a text table that needs a label map.
- Nothing in the pages is tagged. Every offering term and every statement line is found by its words.

## What can be read, by filing (of 732)

| Term | Filings |
|---|---|
| exchange named on the cover | 664 |
| proposed ticker on the cover | 639 |
| shares offered, a count on the cover | 517 |
| underwriting discount named on the cover | 251 |
| fixed offering price on the cover | 125 |
| over-allotment option | 124 |
| price range on the cover | 24 |
| registration-fee table in the main document | 219 |
| amounts declared "in thousands" / "in millions" | 186 / 44 |

Statement lines with a number beside the label: total assets 546, net income 494, total liabilities 477,
weighted shares 458, cash 355, revenue 336, operating income 326, tax 325, lease lines 261, debt 206,
capital spending 210, share-based pay 164, research and development 151. Most 2026 filings are early
registrations with no price yet; that is why the range is so rare.

## Damodaran's model, and what each input needs

His tools value a company by cash flows (a discounted cash flow with a terminal value, options on the shares
taken off equity, research and development and leases turned into capital, the debt ratio and cost of
capital) and price it by multiples against peers. For an offering the answer to compare is the price per
share against the offering price or range.

| Model input | From this feed | Else |
|---|---|---|
| Base revenue, operating income, tax rate | statement lines | none |
| Reinvestment (capital spending, research and development, leases) | statement lines | none |
| Cash, debt, lease debt, shares, options | statement lines | none |
| Offering price or range, shares offered, proceeds | cover | fee table; fee exhibit |
| Cost of capital: beta, equity risk premium, country risk, debt cost | no | his published datasets, as RDM reference data (a provider request, not asked) |
| Peer multiples | no | silver `company_measure` of listed peers |
| First trading price | no | a market data feed, out of scope |

## The silver (three tables, no master field, keyed by accession; decimals NUMBER(38,10), counts BIGINT)

1. `registration_offering`, one row per filing: accession, cik, form, filed_on, effective_on, priced_on,
   shares_offered, shares_sold_by_holders, over_allotment_shares, price_low, price_high, price_fixed,
   currency, discount_per_share, aggregate_offering_price, ticker_proposed, exchange. A term the page does not
   state is empty with its reason (`not stated`, `to be determined`), never zero.
2. `registration_statement_line`, one row per filing, statement, period and line as filed: accession, statement
   (income, balance, cash flow), period_end, period_months, label_as_filed, value, scale (units, thousands,
   millions), currency. Values stay as filed; a parenthesised value is negative. This is the cache of
   `company_fact` for a company with no XBRL history.
3. `registration_valuation_input`, one row per filing, built from table 2 by a reviewed map of labels to line
   items (the `company_line_item` map): base revenue, operating income, operating margin, tax rate, research
   and development, lease liabilities, capital spending, cash, debt, shares, options; each null with a reason
   in the one list of null reasons.

The listed ticker comes from the Security master by the issuer, beside `ticker_proposed` (operator, 2026-10-30).

## The download from SEC, if required

- Required for nothing in tables 2 and 3: the statements are in the main document we hold.
- Optional, one request kind: the filing-fee exhibit, a structured file that states the maximum aggregate
  offering price. 513 of 732 main documents hold no fee table. About 513 requests, about 1.7 hours at the
  capture's 12 s a document, a few MB. **Not requested**: it needs the operator's permission (the earlier
  ruling was "Main doc only"). Recommendation: do not ask; the aggregate price is shares offered times the
  price, and only 24 filings state a range anyway.
- His datasets (betas, risk premium) are a different provider: ask separately, as reference data.

## As built (2026-11-04)

- Two silver tables, not three: `registration_offering` and `registration_statement_line`. The separate
  `registration_valuation_input` is dropped: the statement line's `line_item` (17 line items) is the input of a
  valuation, so no derived table is built.
- Read by the engine alone (Rust): `registration-page.yaml`, no custom code. All 732 filings from 2026 read, none
  refused. Cover terms: exchange 678, ticker 645, shares offered 598, fixed price 159, price range 31, over-allotment
  10. Statement lines: 27,415, of which 25,776 carry a number; income statement 8,268, balance sheet 5,623, cash
  flow 2,284.
- Not measured: how often a value is the wrong column (a percent-of-revenue column can sit beside the amounts;
  the table's heading text, `head`, tells them apart).
