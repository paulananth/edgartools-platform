# 02 Research: how outside vendors and standards set the financials

Gathered 2026-10-21 for tickets 35 (time model), 38 (line items) and 39 (measures), at the operator's request ("use standards from external vendors keep this reserch handy for other decssions"). Later financials decisions (39, 42, 43, 44) read this note first. Public sources only. FactSet's, Bloomberg's and S&P's manuals are behind logins; where only their general practice is known, it is marked **unverified**.

## Sources at a glance

| Source | What it standardizes | Public? |
|---|---|---|
| Compustat (S&P), via WRDS | One record per company and fiscal year (FYEAR); fixed data items (REVT, SALE, NI, IB, OIADP, TXW …) | Item list and FYEAR rules public; full definitions behind WRDS |
| Fundamental Accounting Concepts (FAC, Charles Hoffman, XBRL US work) | About 30 fundamental concepts, each with an ordered "Try Order" of us-gaap concepts, plus impute rules and consistency checks | Public |
| FactSet Fundamentals | Standardized and as-reported data, 750–2,000 items | Item counts only |
| Bloomberg BQL | Fiscal periods by offset from the latest; calendarization by a fiscal-year-end parameter; actuals against estimates | Fact sheet only |
| Intrinio | Company-specific mapping of XBRL tags into standard templates; says mapping documentation is not possible | Statement only |

## 1. Time: periods, years and a changed year end (ticket 35)

- **Compustat keys a year on the month the fiscal year ends.** FYEAR "represents the fiscal year of the current fiscal year-end month": the calendar year of that month, minus one when it is January to May. A short transition period is not a year.
- **A change of year end can give two records in one FYEAR.** Compustat delivers several records with one date, each for a different fiscal-year-end period. Researchers keep the record for the newest year end; one study found 18 such pairs.
- **Calendarization is a separate view.** Bloomberg's BQL has a fiscal-year-end parameter that aligns companies with different year ends to one calendar. Vendors usually show a stub period as its own column and mark growth against it "not meaningful" (**unverified**).
- **Ruled (ticket 35):** every filed copy kept, the latest by default; a year keyed on the period's end date (364–371 days); a changed year end Compustat-style, and a missing year gives null with a reason.

## 2. Line items: which concepts, in which order (ticket 38)

**FAC's Try Order** is the only public, vendor-neutral precedence list found. It agrees with research 01 section 6 wherever both name a line:

| Line | FAC Try Order (first entries) | Research 01 order |
|---|---|---|
| Revenue | `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `…IncludingAssessedTax`, `SalesRevenueNet`, `SalesRevenueServicesNet`, `SalesRevenueGoodsNet`, `RevenuesNetOfInterestExpense`, `RealEstateRevenueNet`, `InterestAndDividendIncomeOperating`, then about 75 industry revenue concepts | Same first four; goods + services only when no total; then four industry concepts |
| Net income attributable to parent | `NetIncomeLoss`, `IncomeLossAttributableToParent` | `NetIncomeLoss`, then `ProfitLoss` − NCI, then `ProfitLoss` flagged |
| Net income including NCI | `ProfitLoss`, `IncomeLossIncludingPortionAttributableToNoncontrollingInterest` | — (used only as a fallback) |
| Equity (including NCI) | `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`, partners' and LLC members' equivalents | Parent equity first: `StockholdersEquity` |
| Operating cash flow | `NetCashProvidedByUsedInOperatingActivities`; continuing and discontinued kept apart | Same; continuing flagged |
| Operating income | `OperatingIncomeLoss`, then income before interest and taxes | `OperatingIncomeLoss` only, no fallback |
| Pretax income | Two continuing-operations concepts, in research 01's order | Same |
| Cost of revenue | `CostOfRevenue`, `CostOfGoodsAndServicesSold`, `CostOfServices`, `CostOfGoodsSold`, then about 20 industry concepts | `CostOfGoodsAndServicesSold` first, then `CostOfRevenue` |
| Gross profit | `GrossProfit` (else imputed) | `GrossProfit`, else revenue − cost of revenue |

- **FAC fills a missing concept with impute rules** (for example, liabilities = current + noncurrent liabilities) and checks each filing with consistency rules. The full rule lists were not readable on the public pages.
- **Compustat keeps totals apart from their parts.** REVT (Revenue – Total) and SALE (Sales/Turnover, Net) are separate items, and excise taxes are their own item (TXW). A total is not replaced by a part.
- **Vendors adjust company by company.** Intrinio says its mapping is company-specific; FactSet and Compustat apply analysts' judgement to each filing (**unverified** in detail). A configured, auditable rule list, as here, cannot do that silently; a value that fails a check goes to a steward instead.

## Measured on the captured cohort (counts only)

- Both `Revenues` and contract revenue (excluding tax) are filed for the same annual period by 99 filers (363 periods). `Revenues` is smaller in 21 periods of 13 filers: in 9 under half, in 10 between 50% and 99%, in 2 within 1%. Six of the 13 have other periods where `Revenues` is the larger.
- The three uncounted concepts are used: `NetIncomeLossAttributableToNoncontrollingInterest` by 133 filers, `MinorityInterest` by 139, `TemporaryEquityCarryingAmountAttributableToParent` by 55.
- `ProfitLoss` gives an annual figure where `NetIncomeLoss` has none for 41 filers (212 periods). Of the 47 filers with 284 missing net income years, `ProfitLoss` fills 46 years, leaving 38 filers with 238.

## 3. Measures: where they live and how they are defined (ticket 39)

- **Vendors store measures.** The WRDS Financial Ratio Suite, built on Compustat, publishes "pre-calculated metrics" at firm and industry level; firm-level ratios are raw, "without any truncation or smoothing" (winsorizing applies only to industry aggregates).
- **Return denominators differ by standard.** WRDS defines after-tax return on average common equity on "average of Common Equity based on most recent two periods"; its quarterly after-tax return on invested capital divides by invested capital lagged a year, only when that is positive (from a copy of the WRDS manual and a forum post; the WRDS pages are behind a login). Damodaran (research 01 section 4) uses beginning-of-period balances. Generic sources use the average of beginning and end.
- **ROIC's capital differs too:** debt plus equity minus (excess) cash is the common form; some definitions use operating assets less non-interest-bearing operating liabilities.
- **"Not meaningful" for growth:** a CAGR is shown as N.M. when the first or last year's value is zero or negative (Nasdaq glossary); a dash means the data is not available. Some vendors keep NA even from a loss to a profit, which drops that case.
- **Windows:** "the number of full fiscal years shown" (Nasdaq); vendors commonly show 1-, 3-, 5- and 10-year growth (**unverified** for each vendor).

## 4. Reading company facts: keys as values, and exact numbers (ticket 40)

- **Keys as values, one level at a time.** The standard tools turn an object's keys into a column one level per call and compose levels laterally: Snowflake `LATERAL FLATTEN` (columns `KEY`, `VALUE`), PostgreSQL `jsonb_each`, Spark `explode` on a map (`key`, `value`), DuckDB `json_each`, jq `to_entries`. The source engine's `each.entries` is the same call; a table takes one iteration, so the deeper levels are flattened downstream (dbt, `LATERAL FLATTEN`).
- **Number range.** RFC 8259 section 6 lets a JSON reader limit range and precision; RFC 7493 (I-JSON) advises numbers within IEEE double. Exact readers keep the number's text (serde_json `arbitrary_precision`; Python's `json` reads integers of any size). Snowflake's `NUMBER` holds up to 38 digits exactly. The engine reads exact 64-bit integers and finite floats, and refuses others.
- **Measured on 368 captured files** (counts only; trial contract `03-company-facts-trial-contract.yaml` beside this note): 367 read in 70.9 s; facts 5,107,788, equal to the long-form copy; concepts 138,987, of which 119 have no facts; nine taxonomies, none unknown; one file refused for one 20-digit cover-page value. With `big_numbers: text` (ticket 128) all 368 read in 75.7 s: facts 5,134,979 and concepts with facts 139,524, both equal to the long-form copy.

## 5. Currencies, IFRS filers and industry formats (ticket 42)

- **Currency.** Compustat carries each company's figures in its reporting currency with an ISO code (`curcd`); Compustat Global has a separate currency file of exchange rates for translation. FactSet's Fundamentals API takes a currency, defaulting to the pricing currency, with `RPT` for the reporting currency. Bloomberg converts on request through the `EQY_FUND_CRNCY` override. So vendors keep the reported currency and convert as a separate step against an exchange-rate source (field definitions **unverified**: the dictionaries are behind logins).
- **IFRS.** Compustat Global standardizes IFRS filers into the same items as its other filers (**unverified** at item level).
- **Industry formats.** Compustat keeps an Industrial format (`INDFMT = INDL`) and a Financial Services format (`FS`) for banks and insurers, with items only financial firms carry (bank capital ratios, insurance business lines); a company can appear in both.
- **Measured on the cohort** (counts only): 52 of 329 filers report some amount in a currency other than USD (EUR 19, GBP 9, CAD 9 lead); 3 report their headline figures (assets, net income, revenue) with no USD figure. 6 filers use `ifrs-full` (2 of them only it); their headline figures are in CAD for 3, EUR for 1, USD for 3. Industry concepts: `Deposits` 44 filers, `InterestAndDividendIncomeOperating` 27, `OperatingLeasesIncomeStatementLeaseRevenue` 21, `PremiumsEarnedNet` 12, `RealEstateInvestmentPropertyNet` 12, `RealEstateRevenueNet` 9, `PolicyholderFunds` 7, `LiabilityForFuturePolicyBenefits` 7, `PublicUtilitiesPropertyPlantAndEquipmentNet` 7, `RevenuesNetOfInterestExpense` 5, `RegulatedAndUnregulatedOperatingRevenue` 3.

## Sources

- [WRDS: Compustat fiscal and calendar dates](https://wrds-support.wharton.upenn.edu/hc/en-us/articles/115003135371-Compustat-Identifying-Fiscal-and-Calendar-Dates)
- [GVKEY and FYEAR duplicates in Compustat](https://robsonglasscock.wordpress.com/2018/04/12/gvkey-and-datadate-or-fyear-duplicates-in-compustat/)
- [Removing duplicate GVKEY-DATADATE](http://kaichen.work/?p=387)
- [CRSP/Compustat income statement items](https://www.crsp.org/wp-content/uploads/ccm_files/IncomeStatementIndustrialAnnual.html)
- [FAC: map from Fundamental Accounting Concepts to us-gaap concepts](https://accounting.auditchain.finance/reporting-scheme/us-gaap/fac/Rules_Mapping/ConceptMap_General-mapping.html)
- [FAC documentation (2016)](http://www.xbrlsite.com/2016/Prototype/FundamentalAccountingConceptsPureXBRL/Documentation/FundamentalAccountingConcepts.html)
- [Bloomberg BQL fundamentals fact sheet](https://www.wu.ac.at/fileadmin/wu/s/library/databases_info_image/Bloomberg_BQL_Fundamentals_FactSheet.pdf)
- [FactSet Fundamentals DataFeed](https://insight.factset.com/resources/at-a-glance-factset-fundamental-datafeed)
- [Intrinio: mapping documentation](https://help.intrinio.com/does-intrinio-provide-mapping-documentation-for-its-standardized-financials)
- [WRDS research data overview (Financial Ratio Suite)](https://wrds-www.wharton.upenn.edu/documents/1400/wrds_research_data_overview.pdf)
- [finsets: WRDS ratios replication notes](https://ionmihai.github.io/finsets/01_wrds/ratios.html)
- [Nasdaq glossary: growth rates](https://www.nasdaq.com/glossary/g/growth-rates)
- [Return on capital (Wikipedia)](https://en.wikipedia.org/wiki/Return_on_capital)
- [TIKR: measuring ROIC](https://www.tikr.com/blog/how-to-measure-return-on-invested-capital-roic-properly)
- [Snowflake FLATTEN](https://docs.snowflake.com/en/sql-reference/functions/flatten)
- [PostgreSQL JSON functions (jsonb_each)](https://www.postgresql.org/docs/current/functions-json.html)
- [RFC 8259, section 6: numbers](https://www.rfc-editor.org/rfc/rfc8259#section-6)
- [RFC 7493 (I-JSON), section 2.2](https://www.rfc-editor.org/rfc/rfc7493#section-2.2)
- [Snowflake numeric types](https://docs.snowflake.com/en/sql-reference/data-types-numeric)

- [Compustat Global manual (WRDS, a university copy)](https://studerende.au.dk/fileadmin/www.medarbejdere.au.dk/it/BSS_Analysevaerktoejer/Finansielle_Databaser/Manual_WRDS_Compustat_Global.pdf)
- [Compustat Global Vantage: industrial and financial services formats](https://business.uc3m.es/en/databases/compustat-global-vantage/)
- [S&P query library: Industrial format (INDFMT = INDL)](https://www.marketplace.spglobal.com/ja/support/query-library/query-(232))
- [FactSet Fundamentals Report Builder (currency parameter)](https://pypi.org/project/fds.sdk.FactSetFundamentalsReportBuilder/1.0.5)
- [Bloomberg currency override (EQY_FUND_CRNCY)](https://www.optuma.com/kb/data/bloomberg-functionality/external-data-fields-bloomberg-override-functionality)
