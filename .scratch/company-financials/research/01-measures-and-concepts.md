# 01 Research: the measures analysts use, and the reported concepts behind each

Ticket: [01](../issues/01-which-measures-and-concepts.md). Map: [map](../map.md). Written 2026-10-12 08:06 ET.

## How this was gathered (and the sec.gov count)

- **Zero requests to sec.gov data endpoints** (data.sec.gov API, companyfacts, frames). Two sec.gov *documentation* pages were read: the EDGAR API page ([link][api]) and the Financial Statement Data Sets PDF ([link][fsds]). Rule L8 in the map requires this disclosure.
- Company facts evidence comes from two local files that already existed. Nothing was fetched.
  - **Cohort.** Ticket 04's capture, `~/.local/share/edgartools/clean-mdm/proving/company-facts/cohort/*.json.gz`, with its manifest `CAPTURE.json` ([04](../issues/04-capture-the-cohorts-company-facts.md)). That is 368 filers with company facts, of which 319 carry a `us-gaap` taxonomy.
  - **Apple.** One cached company-facts file from edgartools' HTTP cache, `~/.edgar/_tcache/data.sec.gov/api-xbrl-companyfacts-CIK0000320193.json` (gzip, fetched 2026-06-09).
- The us-gaap taxonomy files were downloaded from FASB's own host, `xbrl.fasb.org`, for the 2017–2026 schemas, `us-gaap-doc-2026.xml` and `us-gaap-lab-2018-01-31.xml`. Line numbers cited as `FASB doc-2026 L…` refer to [us-gaap-doc-2026.xml][fasbdoc]. Those cited as `FASB xsd-2026 L…` refer to [us-gaap-2026.xsd][fasbxsd].
- Two kinds of local code were read.
  - The old gold models in this worktree, and the old Python concept mapper, deleted in `7f753322` and read via `git show 7f753322^:…`.
  - edgartools 5.30.0, installed at `edgartools-platform/.venv/lib/python3.12/site-packages/edgar/`. Cited below as `edgar/…:line`.
- **Cohort counts are not population counts.** The cohort is the profiling program's 500 fixed entities, so it includes funds and other non-operating filers. Of the 368, 49 have no us-gaap facts at all. A filer counts under every variant it ever used. The exact filters are in the [appendix](#appendix-how-the-cohort-counts-were-computed).
- **No primary source ranks analysts' usage.** The order below follows the ticket's own list. It is supported by the definitions in standard academic sources (Fama–French, Damodaran) and by what this platform computed before. It was not measured.

## 1. How SEC company facts is structured, and what that means for annual series

### Structure

- The top level holds `cik`, `entityName` and `facts`. `facts` is keyed by taxonomy, then by concept. Each concept carries `label`, `description` and `units`. `units` maps a unit (`USD`, `shares`, `USD/shares`, …) to a list of facts.
  - Apple: `{'dei': 2, 'us-gaap': 503}` concepts.
  - Cohort taxonomies: `us-gaap` 319 filers, `dei` 318, `ffd` 132, `ecd` 104, `srt` 101, `invest` 71, `ifrs-full` 6.
- Each fact has the keys `start` (duration facts only), `end`, `val`, `accn`, `fy`, `fp`, `form` and `filed`. Some facts also carry `frame`.
  - Apple's `RevenueFromContractWithCustomerExcludingAssessedTax` has 113 facts. All have the eight keys, and 38 also have `frame`.
  - edgartools' parser reads `val`, `end`, `start`, `filed`, `fy`, `fp`, `form` and `accn`. It never reads `frame` (`edgar/entity/parser.py:177-224`), so edgartools facts lose it.
- The SEC documents the APIs but not these per-fact fields. Per [the API page][api]:
  - Company facts "returns all the company concepts data for a company into a single API call".
  - Company concept returns facts "with a separate array of facts for each units on measure".
  - Frames "aggregates one fact for each reporting entity that is last filed that most closely fits the calendrical period requested".
  - Frame periods are `CY####` for annual data ("duration 365 days +/- 30 days"), `CY####Q#` for quarterly data ("91 days +/- 30 days") and `CY####Q#I` for instants. The APIs update "in real-time", typically "under a minute" after dissemination.
- **`fy` and `fp` belong to the filing, not to the fact.** The Financial Statement Data Sets define `fy` ("Fiscal Year Focus") and `fp` ("Fiscal Period Focus … within Fiscal Year") as fields of the **submission** table (SUB). The number table (NUM) keys a fact by `adsh, tag, version, ddate, qtrs, uom, segments, coreg` ([FSDS PDF][fsds] §3 p.2–3, SUB table p.6, NUM table p.8). The data is "as filed" and "may contain redundancies, inconsistencies, and discrepancies" (§3 p.2). Company facts behaves the same way:
  - In the cohort, 6,767 of 10,640 annual `NetIncomeLoss` facts (64%) have an `fy` that differs from their end year. A 10-K for FY2024 carries FY2022 and FY2023 comparatives, all with `fy=2024`.
  - Within 10-Ks, `fp='FY'` does not mean "annual". Of 19,081 cohort `NetIncomeLoss` facts with `fp=FY` in 10-K forms, only 9,187 have an annual duration. The rest are quarters, such as Q4 or quarterly comparatives. For Apple it is 96 of 153 `fp=FY` facts that are quarterly, e.g. `2008-09-28..2008-12-27` with `fy=2010, fp=FY`.
- **One reported period appears many times.** In the cohort, 3,926 distinct annual `NetIncomeLoss` periods span 10,640 facts, and 3,329 of those periods appear in more than one filing. Apple's us-gaap facts number 24,764, but only 12,216 distinct `(concept, unit, start, end)` remain. Apple's FY2022 revenue (394,328,000,000) appears in its 2022, 2023 and 2024 10-Ks.

### What `frame` does in practice

- **The frame sits on the last-filed copy.** In the cohort, 3,830 annual `NetIncomeLoss` periods carry a frame. In all 3,830 the framed fact is the latest-filed row by `(filed, accn)`, so its value equals the latest value. Apple's FY2022 revenue carries `frame: CY2022` only on the copy in the 2024 10-K. This matches the API's "last filed" rule ([api]).
- **A frame holds one calendar slot, not one fiscal year.** 71 annual periods (1.8%) have no frame.
  - In 66 of them, another period for the same calendar year holds it. Usually the same fiscal year was tagged with a start date one to three days apart. For CIK 12040, `2010-09-30..2011-10-01` holds CY2011 while `2010-10-03..2011-10-01` is unframed. For CIK 36270, `2008-12-31..2009-12-31` holds CY2009 while `2009-01-01..2009-12-31` is unframed.
  - The ±30-day tolerance also lets a frame land on an odd period. For CIK 12040, CY2022 is held by `2021-12-01..2022-10-31`, while its real fiscal year `2021-10-03..2022-10-01` is unframed. The cause was not investigated.
- **Consequence.** `frame` is a usable "latest value" flag for most periods. It is not a fiscal-year key, and it cannot be the only route to an annual series. Deduplicate on `(concept, unit, start, end)` and take the latest `filed`. Keep `frame` as a cross-check.

### Differing values across filings are not only restatements

Grouped by `(concept, unit, start, end)`, Apple has 426 groups whose values differ between filings.

| Cause | Apple example |
|---|---|
| Genuine restatement | The 10-K/A of 2010-01-25 retrospectively changed FY2009 `SalesRevenueNet` from 36,537,000,000 to 42,905,000,000 and `NetIncomeLoss` from 5,704,000,000 to 8,235,000,000 |
| Retroactive stock-split adjustment | FY2012 `EarningsPerShareDiluted` went from 44.15 to 6.31 (7-for-1, in the 2014 10-K). FY2018 went from 11.91 to 2.98 (4-for-1, in the 2020 10-K) |
| Scale and tagging errors | `CommonStockSharesOutstanding` at 2013-09-28 shows 899,213 in one 10-Q against 899,213,000 elsewhere, then 6,294,494,000 after the split |
| Reclassification | FY2016 operating cash flow went from 65,824,000,000 to 66,231,000,000 in the next 10-K |

- Cohort: 152 of 307 filers with annual net income have at least one annual `NetIncomeLoss` period whose value differs across filings. That is 480 periods out of 3,926.
- **Consequence for per-share series.** Use the latest-filed (split-adjusted) value for every year of an EPS or share-count series. Mixing original and later values breaks any per-share CAGR across a split.

### `dei` tags

- The cohort has `dei:EntityCommonStockSharesOutstanding` for 288 filers and `dei:EntityPublicFloat` for 307.
- The dei share count is dated at the **cover page**, not at the balance sheet. Apple's FY2025 10-K gives `end: 2025-10-17`, against a fiscal year ending 2025-09-27.
- edgartools prefers the dei value for `shares_outstanding` and falls back to `us-gaap:CommonStockSharesOutstanding` (`edgar/entity/entity_facts.py:1371-1375`).
- For per-share ratios on a balance-sheet date, use `CommonStockSharesOutstanding` (an instant per FASB xsd-2026 L2429). For EPS-consistent per-share flows, use `WeightedAverageNumberOfDilutedSharesOutstanding`. Use the dei figure only as a last resort, labelled with its own date.

## 2. CAGR definition choices that change results

**The formula.** BEA's annual-rate change is `r = [(x_t / x_0)^(m/n) − 1] × 100`, where `m` is periodicity (1 for annual) and `n` the number of periods between the two levels ([BEA SCB July 2014, Appendix A][bea]). For annual data that reduces to `(end/start)^(1/years) − 1`. The old macro computes exactly this, with `1.0 / years` to avoid integer division (`infra/snowflake/dbt/edgartools_gold/macros/cagr.sql:16-26`). Five choices change the result.

1. **Fiscal versus calendar years.**
   - In the cohort, 73 of the filers with annual net income have no fiscal year ending 31 December.
   - The old models join on `fiscal_year − N` (`financial_factors.sql:170-178`, `financial_derived.sql:71-74`). That `fiscal_year` was the filing's `fy` (old parser `edgar_warehouse/parsers/financials.py:166` at `7f753322^`), not the period's year. The `is_current_period` / `accession_number desc` tiebreaker in `financial_derived.sql:44-58` exists to patch exactly that.
   - Fama–French align fiscal data by "the fiscal year ending in calendar year t−1" ([French, variable definitions][ff]). That is a calendar convention keyed on the period end, not on `fy`.
   - Recommendation: key years on the period `end` date, e.g. the fiscal year whose end falls in calendar year Y. Never key on the filing's `fy`.
2. **Window ends.**
   - The end year must be a complete annual period. An exact `N`-year offset is required: the old test proves a gap yields null rather than a nearby year (`_financial_factors_unit_tests.yml:355-393`).
   - Trailing-twelve-month windows ending at a quarter are a separate choice. They are not specified here, and the map lists them as open.
3. **Negative or zero bases.**
   - The old macro returns null unless both endpoints are strictly positive (`cagr.sql:3-14, 22-24`). `yoy_growth` divides by a negative base and keeps the sign arithmetic (`macros/yoy_growth.sql:1-6`). ROE uses `safe_ratio_signed`, which nulls when equity is ≤ 0 (`financial_factors.sql:137`, `macros/safe_ratio_signed.sql:1-8`).
   - Damodaran: with negative book equity, "the return on equity becomes a meaningless number" ([Damodaran 2007][dam] p.12).
   - How often this bites, from the cohort: the latest annual net income is ≤ 0 for **128 of 307** filers, and the latest 10-K `StockholdersEquity` is ≤ 0 for **54 of 294**. A strict-positive rule therefore nulls net-income CAGR for over 40% of this cohort. The measure needs an explicit "not meaningful" reason code next to the null.
4. **52/53-week years.**
   - 28 cohort filers have at least one 371-day fiscal year. Apple's FY2012, FY2017 and FY2023 are 371 days; the others are 364.
   - 30 filers have fiscal year ends that are not month-ends.
   - Choice: count *years* (BEA's `n` = number of periods), which is standard and leaves the extra week in the growth. The alternative is to annualise by days, `(end/start)^(365.25/days) − 1`. That changes a single-year rate by about 2% of the rate, and almost nothing over five years.
   - Any annual-duration filter must admit 364–371 days. This note used 350–380; the SEC's frame tolerance is 335–395 ([api]).
5. **Restatements and as-of.**
   - "As last reported" uses the latest-filed value for both endpoints, as the frame does. "As first reported" uses each year's own original 10-K.
   - These differ for 152 of 307 cohort filers on net income. They also differ on every per-share series across a split, where only the latest-filed series is consistent.
   - This choice belongs to ticket 03 (time model). It needs a ruling, not a default.

## 3. Measures and the concepts that carry their inputs

**How to read the counts.**

| Column | Meaning |
|---|---|
| `present` | Cohort filers with at least one annual fact (or, for instants, a fact in a 10-K/20-F/40-F) for the concept |
| `recent` | The same, restricted to periods ending on or after 2024-01-01 |
| `first` | Filers whose most recent 10-K is served by this concept under the old priority order |

Totals (`any`) are filers with at least one of the listed concepts. FASB definitions are quoted from doc-2026.

### Revenue (growth, margins, turnover)

`any` 287 / 319 us-gaap filers; 269 with a recent annual period.

| Concept | present | recent | FASB status / meaning |
|---|---|---|---|
| `RevenueFromContractWithCustomerExcludingAssessedTax` | 175 | 159 | ASC 606 revenue "excluding tax collected from customer" (L32966) |
| `Revenues` | 204 | 114 | Total revenue; "Includes … investment and interest income … and sales and trading gain (loss)" (L9185) |
| `RevenueFromContractWithCustomerIncludingAssessedTax` | 51 | 32 | Gross-of-tax variant (xsd L14483) |
| `SalesRevenueNet` | 85 | **0** | "Revenue, Net (Deprecated 2018-01-31)" (FASB lab-2018 L45618); gone from the schema from 2021 |
| `SalesRevenueGoodsNet` / `SalesRevenueServicesNet` | 53 / 37 | 0 / 0 | Deprecated 2018-01-31 (lab-2018 L45444, L45624) |
| `InterestAndDividendIncomeOperating` | 27 | 25 | Bank-style revenue (xsd L5035) |
| `RevenuesNetOfInterestExpense` | 5 | 3 | Broker-dealer style (xsd L8477) |
| `PremiumsEarnedNet`, `RegulatedAndUnregulatedOperatingRevenue`, `OperatingLeasesIncomeStatementLeaseRevenue`, `RealEstateRevenueNet` | 11, 3, 20, 9 | 10, 3, 1, 0 | Industry variants (insurers, utilities, lessors, REITs) |

- **`Revenues` is usually the total, and the contract tag a component.**
  - 104 filers tag both `Revenues` and the contract-excluding-tax concept for the same annual period. In 45 of them the values differ somewhere.
  - In 134 of the 155 differing periods, `Revenues` is the larger. It is always larger for 32 filers, always smaller for 7, and mixed for 6.
  - The old parser and edgartools both put the contract tag first (`git show 7f753322^:edgar_warehouse/parsers/financials_derived.py:41-50`; `edgar/entity/entity_facts.py:864-870`; `edgar/standardization/synonym_groups.py:223-233`). On these filers that picks a component over the total.
- **Concepts change over a filer's life.** Apple used `SalesRevenueNet` for annual periods ending 2007-09-29 to 2017-09-30. It used `Revenues` in the FY2018 10-K (periods 2016–2018), then the contract tag from filings dated 2019 on. A 10-year CAGR must therefore choose a concept **per period**, not once per filer.
- edgartools separates "Revenue" (`Revenues`, `SalesRevenueNet`, …) from "Contract Revenue" as a component (`edgar/xbrl/standardization/concept_mappings.json:3-12`). It also lists names that are not us-gaap elements: `Revenue`, `TotalRevenues`, `NetSales` and `OperatingRevenue` are absent from xsd-2026. The old list had `Revenues` twice and `TotalRevenues` (`financials_derived.py:44-49` at `7f753322^`).

### Net income (growth, margins, ROE, ROA) and EPS

| Concept | present | recent | first | Meaning |
|---|---|---|---|---|
| `NetIncomeLoss` | 304 | 280 | 281 | "attributable to the parent" (L8642) |
| `ProfitLoss` | 212 | 166 | 3 | "consolidated … including the portion attributable to the noncontrolling interest" (L19643) |
| `NetIncomeLossAvailableToCommonStockholdersBasic` | 168 | 106 | 15 | After preferred dividends and participating securities (L8645) |
| `IncomeLossFromContinuingOperations` | 109 | 39 | 0 | Excludes discontinued operations |
| `EarningsPerShareDiluted` | 279 | 264 | 262 | L4133 |
| `EarningsPerShareBasicAndDiluted` | 97 | **0** | 0 | Not in xsd-2026; historical only |
| `IncomeLossFromContinuingOperationsPerDilutedShare` | 106 | 51 | 5 | xsd L3804 |
| `EarningsPerShareBasic` | 284 | 270 | 268 | xsd L1925 |
| `WeightedAverageNumberOfDilutedSharesOutstanding` | 276 | 267 | 265 | xsd L7025 |

- **Pairing rule.** `ProfitLoss` and `NetIncomeLoss` differ for 148 of the 210 filers that tag both (1,200 periods, both directions). So pair parent net income (`NetIncomeLoss`) with parent equity (`StockholdersEquity`). Pair `ProfitLoss` with `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`. Never mix the two in one ratio.
- The old parser fell back from `NetIncomeLoss` to `ProfitLoss` (`financials_derived.py:60-64`) but kept parent-only equity first (`:80-84`). That mixes NCI-inclusive income with parent-only equity.

### Cash flow (OCF growth, FCF, FCF margin)

| Concept | present | recent | first | Meaning |
|---|---|---|---|---|
| `NetCashProvidedByUsedInOperatingActivities` | 306 | 293 | 294 | Includes discontinued operations (L8501) |
| `NetCashProvidedByUsedInOperatingActivitiesContinuingOperations` | 146 | 29 | 5 | xsd L4779 |
| `PaymentsToAcquirePropertyPlantAndEquipment` | 235 | 201 | 199 | PP&E only (L10970) |
| `PaymentsToAcquireProductiveAssets` | 72 | 40 | 31 | PP&E **plus software and intangibles** (L221) |
| `PaymentsToAcquireOtherPropertyPlantAndEquipment`, `PaymentsForCapitalImprovements`, `PaymentsToAcquireRealEstate` | 15, 13, 12 | 7, 3, 6 | 5, 2, 6 | Narrower or industry variants |

- **Free cash flow and EBITDA are not us-gaap elements.** `FreeCashFlow`, `EBITDA` and `CapitalExpenditures` are all absent from xsd-2026. They are non-GAAP measures, which SEC rules require to be reconciled to "the most directly comparable" GAAP measure when a registrant presents them ([17 CFR 229.10(e)(1)(i)(A)-(B)][regsk]). So FCF must be computed as OCF − capex, with the capex concept recorded, because PP&E-only and productive-assets capex differ.
- The old parser listed `CapitalExpenditureDiscontinuedOperations` as a capex fallback (`financials_derived.py:115-119`). That is discontinued-operations capex only (xsd L13756).

### Balance sheet (book value CAGR, ROA, ROE, ROIC, leverage, liquidity)

| Concept | present | recent | first | Meaning |
|---|---|---|---|---|
| `Assets` | 310 | 302 | 300 | Instant, debit (xsd L7211) |
| `Liabilities` | 267 | 259 | 257 | Absent for ~14% of filers that have `Assets` |
| `AssetsCurrent` / `LiabilitiesCurrent` | 252 / 249 | 244 / 241 | — | Unclassified balance sheets (banks, insurers) have none |
| `StockholdersEquity` | 296 | 281 | 279 | Parent; "Excludes temporary equity and … noncontrolling interest" (L17405) |
| `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` | 164 | 126 | 18 | L19907 |
| `PartnersCapital` / `MembersEquity` | 4 / 9 | 3 / 1 | — | Partnerships, LLCs |
| `CashAndCashEquivalentsAtCarryingValue` | 290 | 240 | 238 | xsd L2087 |
| `CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents` | 260 | 247 | 49 | Cash-flow-statement total; includes restricted cash |
| `LongTermDebtNoncurrent` | 155 | 115 | 114 | Noncurrent only (L7862) |
| `LongTermDebt` | 208 | 137 | 51 | **Current plus noncurrent** (L7901) |
| `LongTermDebtCurrent` | 147 | 99 | 98 | L7829 |
| `DebtCurrent` | 52 | 28 | 15 | "debt and lease obligation, classified as current" (L2852) |
| `LongTermDebtAndCapitalLeaseObligations` | 53 | 34 | 17 | Noncurrent, including leases (L2855) |
| `ShortTermBorrowings` / `CommercialPaper` / `NotesPayableCurrent` | 73 / 20 / 57 | 43 / 8 / 26 | — | Short-term debt variants |
| `CommonStockSharesOutstanding` | 253 | 226 | 224 | Instant shares (L2243) |

- **`LongTermDebt` already includes the current portion.** Where a filer tags both it and `LongTermDebtNoncurrent` for the same date (139 of 147 such filers differ), `LongTermDebt` is the larger in 2,342 of 2,396 differing dates.
- So total debt is one of:
  - `LongTermDebt` + short-term borrowings, or
  - `LongTermDebtNoncurrent` + `LongTermDebtCurrent` (or `DebtCurrent`) + short-term borrowings.
- It is never `LongTermDebt` + `LongTermDebtCurrent`.

### Other inputs (operating margin, ROIC, EBITDA, payout)

| Line item | Concepts in priority order | Counts | Note |
|---|---|---|---|
| Operating income | `OperatingIncomeLoss` | 250 present, 234 recent | Absent for ~22% of us-gaap filers: banks, insurers, single-step income statements |
| Pretax income | `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`, then `…MinorityInterestAndIncomeLossFromEquityMethodInvestments` | first choice 242 | — |
| Income tax | `IncomeTaxExpenseBenefit` | 285 | — |
| Interest expense | `InterestExpense`, `InterestExpenseNonoperating`, `InterestExpenseOperating`, `InterestExpenseDebt`, `InterestAndDebtExpense` | 218 / 112 / 35 / 79 / 28 present | `InterestExpense` has only 68 recent filers; `InterestExpenseNonoperating` (xsd L18392) has 111, a recent taxonomy shift |
| D&A | `DepreciationDepletionAndAmortization` (L19796), `DepreciationAndAmortization`, `DepreciationAmortizationAndAccretionNet`, `Depreciation` | 196 / 134 / 35 / 219 | `Depreciation` alone excludes amortization |
| Cost of revenue | `CostOfGoodsAndServicesSold`, `CostOfRevenue`, `CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization` | 134 / 86 / 13 | `CostOfGoodsSold` and `CostOfServices`: 68 / 30 present, 0 recent |
| Gross profit | `GrossProfit` | 142 present | Only 142 report it; otherwise revenue − cost of revenue |
| Dividends | `PaymentsOfDividendsCommonStock`, `PaymentsOfDividends` | 109 / 92 | — |
| Buybacks | `PaymentsForRepurchaseOfCommonStock` | 197 | — |
| Dividends per share | `CommonStockDividendsPerShareDeclared`, `CommonStockDividendsPerShareCashPaid` | 117 / 73 | — |

Cross-check: edgartools' own learned occurrence rates across 337 companies agree in direction. `Assets` 0.997, `NetCashProvidedByUsedInOperatingActivities` 0.976, `EarningsPerShareDiluted` 0.917, `Revenues` 0.427 against the contract tag at 0.383, `LongTermDebtNoncurrent` 0.309 (`edgar/entity/data/statement_mappings_v1.json:5`, mapping entries at `:196, :493, :460, :625, :801, :262`). That file keeps only concepts above a threshold, so an absence there does not mean zero.

## 4. Measure definitions (inputs → formula), from primary sources

| Measure | Formula and source | Inputs |
|---|---|---|
| Revenue, net income, EPS, OCF, FCF, book value CAGR | `(X_end / X_start)^(1/n) − 1` ([BEA][bea]); FCF = OCF − capex (non-GAAP, [Reg S-K 10(e)][regsk]) | Lines above; book value = `StockholdersEquity` |
| Gross, operating and net margin | GP/Revenue, OpInc/Revenue, NI/Revenue (old: `financial_factors.sql:133-136`) | — |
| ROE | Net income_t / Book equity_{t−1} — **beginning** equity ([Damodaran][dam] p.11). The old model used ending equity (`financial_factors.sql:137`) | `NetIncomeLoss`, `StockholdersEquity` |
| ROA | NI / Assets (old used ending assets, `financial_factors.sql:138`) | — |
| ROIC | EBIT(1−t) / (BV debt + BV equity − cash), with capital from the start of the period ([Damodaran][dam] pp.7–10). The old ROIC was pre-tax EBIT/(equity + debt) with ending capital and no cash netting (`financials_derived.py:279-283` at `7f753322^`) | `OperatingIncomeLoss`, tax rate from `IncomeTaxExpenseBenefit` / pretax, debt, equity, cash |
| Operating profitability (Fama–French) | (Revenue − COGS − interest − SG&A) / (book equity + minority interest) ([French][ff]) | — |
| Investment / asset growth | ΔAssets_{t−2→t−1} / Assets_{t−2} ([French][ff]); old `asset_growth_yoy` (`financial_factors.sql:121-124`) | — |
| Leverage | Debt/Assets, Debt/Equity, Liabilities/Assets; current ratio CA/CL (old `financial_factors.sql:110-118`) | — |
| Per-share | EPS as reported; book value per share = `StockholdersEquity` / `CommonStockSharesOutstanding` at the same instant; FCF per share = FCF / `WeightedAverageNumberOfDilutedSharesOutstanding` | Latest-filed (split-adjusted) series only |

## 5. Hazards in the old code and in edgartools (do not carry over)

1. The old parser counted `LineOfCreditFacilityRemainingBorrowingCapacity` as short-term debt (`financials_derived.py:98-103` at `7f753322^`). It is **undrawn capacity** (FASB doc-2026 L7565).
2. `LiabilitiesAndStockholdersEquity` was used as a fallback for total liabilities. This is in the old parser (`financials_derived.py:75-78`) and in edgartools (`edgar/entity/entity_facts.py:961`). It is total assets.
3. edgartools falls back from `Assets` to `AssetsCurrent` (`edgar/entity/entity_facts.py:933`).
4. The old parser used `CommonStockSharesIssued` as a fallback for shares outstanding (`financials_derived.py:154-157`). Issued includes treasury shares. edgartools groups `WeightedAverageNumberOfSharesOutstandingBasic` under "common shares outstanding" (`edgar/standardization/synonym_groups.py:678-683`). That is a period average, not an instant.
5. edgartools maps `IncomeTaxesPaidNet` (cash paid) to income tax expense (`edgar/xbrl/standardization/concept_mappings.json:104-105`, `synonym_groups.py:341`). It maps `InterestIncomeExpenseNet` (net of interest income) to interest expense (`concept_mappings.json:84-87`, `synonym_groups.py:308`). It puts `AmortizationOfIntangibleAssets` alone under D&A (`synonym_groups.py:389`).
6. The old parser built total debt by summing whichever "long" and "short" concepts matched first (`financials_derived.py:248-252`). With `LongTermDebt` first-matched and `CurrentPortionOfLongTermDebt` as the short leg, the current portion is counted twice. `CurrentPortionOfLongTermDebt` is not a us-gaap element in xsd-2026 either.
7. Old and edgartools selection is "first concept with a value, per filing or per filer". It is never stitched per period with a recorded concept. edgartools `get_annual_fact` treats `fp=='FY'` as annual (`edgar/entity/entity_facts.py:685`), which admits quarterly facts (§1). `get_fact` returns the latest by `(filing_date, period_end)` (`:649`), which mixes periods.
8. Keying on the filing's `fy` (old parser `financials.py:166`, edgartools `parser.py:193`) instead of the period end. See §2.1.
9. The old parser read only `us-gaap` (`financials.py:84-90`). It hardcoded `segment='consolidated'` (`:178`) and kept every unit, with no currency check. The cohort has non-USD units, e.g. `NetIncomeLoss` in CAD (2 filers) and EUR (1), and `Revenues` in AFN (1). Six filers use `ifrs-full`.

## 6. Recommendation: standard line items in analyst-usage order, each with an ordered concept list

**Rules that apply to every line.**

- Pick per `(filer, period)`: the first concept that has a fact for that exact period, deduplicated on `(concept, unit, start, end)`. Keep the latest `filed` copy, with `frame` as a cross-check.
- Record the chosen concept and the `accn` beside each value.
- Annual means a 350–380-day duration, keyed by the calendar year of `end`. Instants are matched on `end`.
- USD only, unless ruled otherwise.

1. **Revenue.**
   1. `Revenues`
   2. `RevenueFromContractWithCustomerExcludingAssessedTax`
   3. `RevenueFromContractWithCustomerIncludingAssessedTax`
   4. `SalesRevenueNet` (historical, before 2018)
   5. `SalesRevenueGoodsNet` + `SalesRevenueServicesNet`, only when both exist and no total does (historical)
   6. `RevenuesNetOfInterestExpense`
   7. `InterestAndDividendIncomeOperating` (banks)
   8. `RegulatedAndUnregulatedOperatingRevenue` (utilities)
   9. `PremiumsEarnedNet` (insurers)

   Industry variants 6–9 are flagged by kind. `Revenues` goes first because it is the FASB total, and it was the larger value in 134 of 155 differing periods. Revisit with ticket 06 for the 7 filers where it is smaller.
2. **Net income attributable to parent.**
   1. `NetIncomeLoss`
   2. `ProfitLoss` − `NetIncomeLossAttributableToNoncontrollingInterest` (when both exist)
   3. `ProfitLoss`, flagged "includes NCI" and paired with NCI-inclusive equity
3. **Diluted EPS.**
   1. `EarningsPerShareDiluted`
   2. `EarningsPerShareBasicAndDiluted` (historical)
   3. `IncomeLossFromContinuingOperationsPerDilutedShare`, flagged "continuing operations"

   Use the latest-filed series (split-adjusted).
4. **Operating cash flow.**
   1. `NetCashProvidedByUsedInOperatingActivities`
   2. `NetCashProvidedByUsedInOperatingActivitiesContinuingOperations`, flagged
5. **Capital expenditure** (for free cash flow).
   1. `PaymentsToAcquirePropertyPlantAndEquipment`
   2. `PaymentsToAcquireProductiveAssets`, flagged "includes software and intangibles"
   3. `PaymentsToAcquireOtherPropertyPlantAndEquipment`
   4. `PaymentsForCapitalImprovements`

   Free cash flow = item 4 − item 5. It is a computed, non-GAAP value.
6. **Book value (parent equity).**
   1. `StockholdersEquity`
   2. `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` − `MinorityInterest`
   3. `PartnersCapital`
   4. `MembersEquity`
7. **Total assets.** `Assets` only. No fallback.
8. **Diluted weighted-average shares.**
   1. `WeightedAverageNumberOfDilutedSharesOutstanding`
   2. `WeightedAverageNumberOfShareOutstandingBasicAndDiluted` (historical)
9. **Shares outstanding (instant).**
   1. `CommonStockSharesOutstanding`
   2. `dei:EntityCommonStockSharesOutstanding`, flagged "cover-page date"
10. **Gross profit.**
    1. `GrossProfit`
    2. Revenue − cost of revenue, using `CostOfGoodsAndServicesSold`, then `CostOfRevenue`, then `CostOfGoodsSold`, then `CostOfServices`
11. **Operating income.** `OperatingIncomeLoss`. No fallback. Null for single-step and financial filers rather than a pretax substitute.
12. **Total debt.** One of:
    - `LongTermDebt` + (`ShortTermBorrowings` or `CommercialPaper` or `NotesPayableCurrent`), or
    - `LongTermDebtNoncurrent` + (`LongTermDebtCurrent` or `DebtCurrent`) + short-term borrowings, or
    - `LongTermDebtAndCapitalLeaseObligations` + `LongTermDebtAndCapitalLeaseObligationsCurrent`, flagged "includes leases"

    Never `LongTermDebt` + `LongTermDebtCurrent`. Never borrowing capacity.
13. **Cash and equivalents.**
    1. `CashAndCashEquivalentsAtCarryingValue`
    2. `CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`, flagged "includes restricted cash"
    3. `Cash`
14. **Total liabilities.**
    1. `Liabilities`
    2. `LiabilitiesAndStockholdersEquity` − `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` − `TemporaryEquityCarryingAmountAttributableToParent`, if present, as a computed value and flagged
15. **Current assets and current liabilities.** `AssetsCurrent` and `LiabilitiesCurrent`. Null for unclassified balance sheets.
16. **Pretax income and income tax** (for the ROIC tax rate).
    1. `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`
    2. `IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments`

    Then `IncomeTaxExpenseBenefit`.
17. **Interest expense.**
    1. `InterestExpense`
    2. `InterestExpenseNonoperating`
    3. `InterestExpenseDebt`
    4. `InterestAndDebtExpense`
    5. `InterestExpenseOperating`

    Never `InterestIncomeExpenseNet`.
18. **Depreciation and amortization.**
    1. `DepreciationDepletionAndAmortization`
    2. `DepreciationAndAmortization`
    3. `DepreciationAmortizationAndAccretionNet`
    4. `Depreciation`, flagged "excludes amortization"
19. **Dividends and buybacks.**
    - Dividends paid: `PaymentsOfDividendsCommonStock`, then `PaymentsOfDividends`.
    - Buybacks: `PaymentsForRepurchaseOfCommonStock`.
    - Dividends per share: `CommonStockDividendsPerShareDeclared`, then `CommonStockDividendsPerShareCashPaid`.

Three concepts in the list were not counted in the cohort, but each exists in us-gaap 2026: `NetIncomeLossAttributableToNoncontrollingInterest` (xsd-2026 L9218), `MinorityInterest` (L4729) and `TemporaryEquityCarryingAmountAttributableToParent` (L11449). Count their cohort coverage in ticket 06 before relying on them. Two historical concepts, `EarningsPerShareBasicAndDiluted` and `WeightedAverageNumberOfShareOutstandingBasicAndDiluted`, are not in xsd-2026.

## Open for later tickets

- **Ticket 03.** Pick "as last reported" or "as first reported" as the default for CAGR endpoints.
- **Ticket 06.** Check the 7 filers whose `Revenues` is below their contract revenue.
- **Not covered here:**
  - Industry statement shapes (banks, insurers, REITs)
  - IFRS filers (6 in the cohort)
  - Deriving Q4 and trailing-twelve-month figures (the map lists these as not yet specified)

## Appendix: how the cohort counts were computed

The input was every `*.json.gz` under `~/.local/share/edgartools/clean-mdm/proving/company-facts/cohort/` (368 files, listed in `CAPTURE.json`). Each was opened with Python's `json` and `gzip`. The scripts were run with `python3 -I` from the session scratchpad, which is not kept, so their exact filters are recorded here.

**Common filters.**

- *Annual* = a fact with `start`, and `350 <= (end − start).days <= 380`.
- `present` = any fact for the concept in a form starting `10-K`, `20-F` or `40-F`. For duration concepts it must also be annual; instants need only one fact.
- `recent` = the same, with `end >= 2024-01-01`.
- `first` = walk the concept list in the order shown and take the first concept with a fact where `end >= 2024-01-01` and the form starts `10-K`.

**Time-model statistics** (all on `us-gaap:NetIncomeLoss`, all units).

- Facts: 57,550 in total, 16,144 framed.
- `fp=FY` in 10-K forms: 19,081, of which 9,187 annual.
- Annual facts: 10,640, of which 6,767 have `fy != year(end)`.
- Distinct annual `(start, end)` periods: 3,926. Of these, 3,329 appear in more than one filing, and 480 carry more than one distinct `val`.
- **Restatements by filer.** 152 filers have at least one such period.
- **52/53-week and year-end checks.**
  - A 371-day year means `(end − start).days + 1 == 371` on a distinct annual period.
  - A non-month-end year is an annual `end` not on a calendar month-end.
  - No December year-end means no annual `end` on `-12-31`.
- **Sign of the latest values.**
  - The latest annual net income is the annual fact with the greatest `(end, filed)`.
  - The latest equity is the 10-K `StockholdersEquity` fact with the greatest `(end, filed)`.
- **Frame check.** Over annual USD `NetIncomeLoss` periods (3,901 here; the 25 fewer than above are the other-currency units), the framed fact was compared with the row that has the greatest `(filed, accn)`.
- **Unframed periods.** Each was tested for whether a `CY{year}` frame for a nearby calendar year is held by a different `(start, end)` on the same concept.
- **Pairwise comparisons** over shared annual USD periods.
  - `Revenues` against `RevenueFromContractWithCustomerExcludingAssessedTax`.
  - `ProfitLoss` against `NetIncomeLoss`.
  - The same for `LongTermDebt` against `LongTermDebtNoncurrent` on shared instant `end` dates.
  - For each pair: count the filers and periods that differ, and the direction of `|A|` against `|B|`.

**Apple** (`CIK0000320193`, from the cache file above). The same deduplication and grouping, plus a listing of the groups whose `val` differs, of revenue concepts by annual period end, and of the annual durations.

[api]: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
[fsds]: https://www.sec.gov/files/financial-statement-data-sets.pdf
[fasbdoc]: https://xbrl.fasb.org/us-gaap/2026/elts/us-gaap-doc-2026.xml
[fasbxsd]: https://xbrl.fasb.org/us-gaap/2026/elts/us-gaap-2026.xsd
[bea]: https://apps.bea.gov/scb/pdf/2014/07%20July/Dpages/0714dpg%20_appendix_a.pdf
[ff]: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/variable_definitions.html
[dam]: https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/returnmeasures.pdf
[regsk]: https://www.law.cornell.edu/cfr/text/17/229.10
