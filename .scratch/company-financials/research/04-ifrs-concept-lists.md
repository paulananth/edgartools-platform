# 04 Research: the IFRS concept for each line item

Gathered 2026-10-22 for ticket 44 (the answer key) and build ticket 46 (the line
items in rules configuration). The operator ruled on 2026-10-22, ticket 42:
"IFRS mapped into the same 19 items: an ordered `ifrs-full` list beside each
`us-gaap` list". Then, ticket 44: "Propose from IFRS taxonomy (Recommended)".
Later financials decisions read this note beside research 01 and 02.

## Sources

- **The IFRS Accounting Taxonomy**, published by the IFRS Foundation each year
  (2024, 2025). Its `ifrs-full` elements are modelled on the IFRS Standards'
  own line items (IAS 1 for the statements, IAS 7 for cash flows, IAS 33 for
  earnings per share). The element names below are the taxonomy's own.
- **What the cohort's IFRS filers file.** 6 of the 368 cohort companies file
  `ifrs-full` facts; the count beside each concept is how many of the 6 use it.
  A name the cohort never uses is marked "not in the cohort": it is still a
  taxonomy element, kept for filers outside the cohort.
- **No outside mapping was found.** A search found no public, vendor-neutral
  mapping of IFRS elements to fundamentals, as FAC's Try Order is for US GAAP
  (research 02). Vendors map IFRS filers into their standard templates
  company by company (**unverified**: their manuals are behind logins).

## The rules every list follows (as for us-gaap, research 01 section 6)

- **First present wins**, per filer and annual period, using the latest-filed
  copy. The chosen concept and accession are recorded beside the value.
- **Flags and computed fallbacks** mean what they mean for us-gaap.
- **The reporting currency stays as filed, with its ISO code** (ticket 42).
- **A filer is read from the taxonomy it files in, period by period**, because
  one cohort company moves from `ifrs-full` to `us-gaap` within its history.

## The lists

| # | Line item | `ifrs-full`, in order (cohort filers of 6) |
|---|---|---|
| 1 | Revenue | `Revenue` (5); `RevenueFromContractsWithCustomers` (3); banks: `RevenueFromInterest` (3), then `InterestRevenueCalculatedUsingEffectiveInterestMethod` (not in the cohort); insurers: `InsuranceRevenue` (1). The industry ones are flagged by kind, as for us-gaap |
| 2 | Net income attributable to parent | `ProfitLossAttributableToOwnersOfParent` (5); `ProfitLoss` − `ProfitLossAttributableToNoncontrollingInterests` (5, 4), computed; `ProfitLoss`, flagged "includes NCI" |
| 3 | Diluted EPS | `DilutedEarningsLossPerShare` (5); `BasicAndDilutedEarningsLossPerShare` (1); `DilutedEarningsLossPerShareFromContinuingOperations` (2), flagged "continuing operations" |
| 4 | Operating cash flow | `CashFlowsFromUsedInOperatingActivities` (6) |
| 5 | Capital expenditure | `PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities` (5); `PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets` (1), flagged "includes intangibles and other assets" |
| 6 | Book value (parent equity) | `EquityAttributableToOwnersOfParent` (5); `Equity` − `NoncontrollingInterests` (6, 4), computed |
| 7 | Total assets | `Assets` (6). No fallback |
| 8 | Diluted weighted-average shares | `AdjustedWeightedAverageShares` (5). Not `WeightedAverageShares`, which is basic |
| 9 | Shares outstanding (instant) | `NumberOfSharesOutstanding` (3); `dei:EntityCommonStockSharesOutstanding`, flagged "cover-page date" |
| 10 | Gross profit | `GrossProfit` (3); `Revenue` − `CostOfSales` (2), computed |
| 11 | Operating income | `ProfitLossFromOperatingActivities` (4). No fallback. IAS 1 defines no operating profit, so the line is empty where a filer does not present one. IFRS 18, required from 2027, defines "operating profit": revisit then |
| 12 | Total debt | `Borrowings` (3); else `LongtermBorrowings` + `ShorttermBorrowings` (5, 2); else `CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings` + `LongtermBorrowings` (2, 5). Lease liabilities (`LeaseLiabilities`, 6) are kept apart, never added: under IFRS 16 every lease is a liability, and adding them would make IFRS filers' debt incomparable to US GAAP filers' |
| 13 | Cash and equivalents | `CashAndCashEquivalents` (6); `Cash` (5), flagged "cash only" |
| 14 | Total liabilities | `Liabilities` (6); `EquityAndLiabilities` − `Equity` (6, 6), computed |
| 15 | Current assets and liabilities | `CurrentAssets` (5) and `CurrentLiabilities` (5). Empty for a balance sheet presented by liquidity, as banks present it |
| 16 | Pretax income and income tax | `ProfitLossBeforeTax` (5); then `IncomeTaxExpenseContinuingOperations` (5) |
| 17 | Interest expense | `InterestExpense` (4); `InterestExpenseOnBorrowings` (2); `FinanceCosts` (3), flagged "includes other finance costs" |
| 18 | Depreciation and amortisation | `DepreciationAndAmortisationExpense` (3); `AdjustmentsForDepreciationAndAmortisationExpense` (3), the cash-flow add-back; `DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss` (2), flagged "includes impairment"; `DepreciationExpense` (3), flagged "excludes amortisation" |
| 19 | Dividends and buybacks | Dividends paid: `DividendsPaidClassifiedAsFinancingActivities` (1), `DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities` (1), `DividendsPaid` (1). Buybacks: `PaymentsToAcquireOrRedeemEntitysShares` (2). Dividends per share: `DividendsRecognisedAsDistributionsToOwnersPerShare` (not in the cohort) |

## Where IFRS differs from the us-gaap lists, and why

- **Operating income may be empty.** IAS 1 has no defined operating profit, so
  no fallback is invented. A measure that needs operating income is null with
  "no concept filed".
- **Lease liabilities stay out of total debt** (line 12). That is the
  comparable choice, since US GAAP keeps operating leases out of debt; the US
  GAAP list adds finance leases only when flagged. **Unverified**: vendors
  differ here.
- **Diluted shares have one concept.** The basic count is never a fallback,
  the same rule as us-gaap's.
