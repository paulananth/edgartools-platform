# 02 Research: how outside vendors and standards set the financials

Gathered 2026-10-21 for tickets 35 (time model) and 38 (line items), at the operator's request ("use standards from external vendors keep this reserch handy for other decssions"). Later financials decisions (39, 42, 43, 44) read this note first. Public sources only. FactSet's, Bloomberg's and S&P's manuals are behind logins; where only their general practice is known, it is marked **unverified**.

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
