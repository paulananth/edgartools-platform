# Fundamentals acquisition requirements from the valuation workbook

Source: `Financial-Model-and-Valuation-Template.xlsx`, v1.2 shown in the workbook.
SHA256: `446e2eddbb976d4538aa9488c9e457164ce3a55d77ca8fdaba345297f76110a6`.
Inspected all seven sheets, 3,862 populated/formula cells, 3,132 formulas (including
expanded shared formulas), defined names, comments, drawing text and instructional
images. Original workbook unchanged; no external workbook links or SEC data API
requests followed. This is a requirements catalog, not implemented acquisition.

There are **115 catalog entries**: 25 reported financial inputs, 20 reported reconciliation additions, 7 supplemental disclosures, 6 market and valuation observations, 19 versioned model assumptions, 24 computed outputs, 14 context and provenance. The raw acquisition list is the reported inputs, reconciliation additions,
conditional supplemental disclosures and relevant market observations. Assumptions
and computed outputs are deliberately identified separately so they do not become
fake source facts.

## What to acquire

1. **Revenue:** consolidated revenue plus every disclosed business/product/service/
   geographic revenue line and its label/context; relevant operating drivers.
2. **Income statement:** cost of revenue, S&M, R&D, G&A, depreciation (amortization
   separately when available), other income/expense, pretax income, tax expense/
   benefit, net income and the common-shareholder numerator, basic/diluted EPS and
   their weighted-average share denominators. Reported totals validate the model.
3. **Balance sheet:** cash, short-term investments, net receivables, inventory,
   net PP&E, payables, short-term borrowings/current debt maturities/non-current
   debt, retained earnings, monetary common share capital and APIC; opening
   balances and reported asset/liability/equity totals for reconciliation.
4. **Cash flow:** cash PP&E purchases/capex, reported CFO/CFI/CFF, cash/FX bridge,
   actual debt/equity cash transactions, buybacks/dividends and other material
   operating adjustments. Do not use changes in share capital as cash issuance.
5. **Notes/IR:** applicable NOL schedules, deferred revenue, acquisitions and
   perimeter changes, company guidance, business drivers/KPIs, TAM evidence and share/capital actions.
6. **Valuation observations:** current share-class price and actual outstanding
   shares with dates/currency; optional price/benchmark history, risk-free yield, currency-conversion
   observations and interest/debt-term evidence when calibrating the model assumptions.
7. **Every record:** identity, actual fiscal dates, instant/duration/YTD context,
   source filing/publication vintage, taxonomy/concept/dimensions, units/currency/
   precision, immutable source hash, mapping lineage and availability status.

## Historical window and normalization

The workbook's first forecast-year input is `Step 2 Revenue Forecast!E4` (2024
in this file). It models five preceding fiscal years, each with four quarterly
observations and an annual total, then five forecast years (the first also has
quarterly estimates). For this saved template, historical labels are 2019–2023
and forecasts are 2024–2028. These dates are placeholders driven by E4.

Supply at least that historical window plus opening positions before its first
quarter; retain older available reported history for the separately planned
all-years/CAGR program. Use issuer fiscal dates, including non-calendar and
52/53-week years. Cash-flow and other duration facts may be reported YTD: preserve
the original duration and derive standalone quarters only from compatible
vintages/units/definitions. Fiscal labels alone are not a unique fact key.

Store raw amounts and currency/unit metadata; presentation in the workbook is
currency amounts in thousands and share counts in thousands. EPS and stock price
remain per-share amounts. Keep annual/quarter weighted-average shares, period-end
outstanding shares and monetary share capital as three different concepts.

## Source routes

Start with Company Facts for applicable standard-taxonomy, entity-wide reported
concepts; do not promise coverage for every field. SEC documents this aggregation
scope in its [API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
Custom concepts, segment/dimension revenue, NOL details and supporting narrative
may require original filing/iXBRL/notes and issuer IR materials. Company Facts
alone does not satisfy the complete workbook requirements.

Retain filing content/presentation for validation. The SEC's [Financial Statement
Data Sets](https://www.sec.gov/dera/data/financial-statement-data-sets.html) provide
numeric primary-statement data; the [Statement and Notes Data Sets](https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets)
provide detailed numbers/text from statements and notes. These are source-route
candidates; no feed, taxonomy mapping, rights or production qualification is
established by this list. Non-SEC market/IR data requires an approved source route.

## Model configuration, not acquisition

Store period/scenario/versioned assumptions for revenue and expense growth/ratios,
working capital, capex, future investments/debt/shares, monetary equity balances,
other income/expense, tax/NOL utilization,
capital mix, risk-free rate, beta, expected market return, debt cost, terminal
growth, revenue/PEG multiples and investor required return. The defaults in the
workbook are examples, not company observations or recommended investments.

Compute ratios/growth, totals, margins, EPS, modeled cash flow/FCF, WACC,
DCF/terminal value, sensitivity and valuation targets from observations and
approved assumptions. Keep reported equivalents as independent reconciliation
facts. This workbook explicitly shows YoY/QoQ; CAGR is part of the earlier parked
program, not an explicit additional cell output in this file.

## Workbook issues that change acquisition requirements

- **G01 History and fiscal periods** (S2 E4,B6:AI6; S3 C7:AJ7): Five historical years x four quarters plus annuals; first forecast year has quarters, followed by four annual forecasts. Template 2024 is an input/default, not the current year. Keep actual fiscal calendars and older source history.
- **G02 Balance opening positions** (S4 B10,B18,B39; S5 B27): Acquire opening cash, PP&E, retained earnings and working-capital balances before first modeled quarter. First modeled values are simplified; do not replace actual opening balances with zero.
- **G03 Share definitions** (S3 C60,G62; S4 A40; S6 D72/SHARES; S7 I3): Define basic versus diluted weighted-average shares separately from monetary common share capital and current outstanding shares. Annual GAAP Shares copies Q4; DCF SHARES points to AB62 (forecast Q1). These are not observed annual/current share definitions.
- **G04 Revenue segments/custom concepts** (S2 A7,A13,A18; S1 Important Notes): Two line labels are placeholders. Acquire all actually disclosed revenue dimensions/drivers. SEC Company Facts only aggregates standard-taxonomy/entity-wide facts, so filing/iXBRL/IR supplementation is needed for dimensions/custom labels.
- **G05 Cash-flow completeness** (S5 A8:A30; S4 A40): Modeled CFO includes only net income, depreciation, AR/inventory/AP changes; modeled financing uses debt and common-capital changes. Acquire reported CFO/CFI/CFF and actual cash transactions for independent reconciliation.
- **G06 Reported balance-sheet coverage** (S4 B42,A41,A45): Workbook B42 sums B39:B40 and omits APIC row41. Real equity may include treasury stock, OCI and NCI; real asset/liability categories may include goodwill, intangibles, leases and deferred tax. Keep reported totals, not a forced balance.
- **G07 PP&E and cash capex** (S4 B18,A21; S5 A16): Acquire net PP&E and cash purchases separately. Balance changes alone do not identify cash capex because depreciation, non-cash additions, acquisitions, disposals and FX differ.
- **G08 Expense overlap and adjusted EPS** (S3 A13:A48; A64 comment): Do not double-count D&A already in cost/operating expenses. Template EBITDA adds depreciation only; A64 excludes only depreciation, not a company-disclosed non-GAAP reconciliation.
- **G09 Quarterly/YTD/annual normalization** (S2 quarter/year columns; S3 G62; S5 annual columns): Acquire raw periods and dates. Derive standalone duration quarters only from compatible observations; Q4 can be annual less nine months for additive flows. Never apply that subtraction to balances, ratios, EPS or weighted-average shares.
- **G10 Taxes and loss carryforwards** (S3 C54:Z54 and comments; S1 note8): Historical tax formulas contain example hard-coded rates. Acquire actual tax provision/benefit and pretax income, with NOL/tax-note context; future rates/utilization are assumptions.
- **G11 DCF cash-flow basis and timing** (S5 B33; S6 C11:G11,D63,D70:D73): Resolve whether the cash flows are equity or firm cash flows, the debt/cash/equity bridge and discount timing. There are five forecast FCF values but terminal discount uses exponent4. Do not adopt the workbook as a qualified production valuation definition.
- **G12 Market data versus assumptions** (S6 F35,F37,F39,F46,F62,G23; S7 E3,I4,C13/C17/C21): Share price is an observed external input. Risk-free/beta/return/debt-cost/growth/weights/multiples are modeled assumptions; optional calibration requires as-of, instrument/window and methodology. IPO estimated price is an assumption, not a traded observation.
- **G13 Missing facts, scaling and currency** (S2:S7 monetary headers; S3 A62; placeholder zeros/N/A): Statements use thousands and shares use thousands; EPS/price are per share. Preserve real currency, units, negatives, precision and non-applicability. Zero template values are not acquired data; real reported zeros remain valid.
- **G14 External reference** (Defined name Market_Cap): One name points to an external workbook; no extracted cell formula uses it. No external link was followed. The visible I3 market cap is computed locally from price and modeled shares.

## Full catalog

Sheet aliases: `S1` = `Step 1 Modeling+Valuation Rules`; `S2` = `Step 2 Revenue Forecast`; `S3` = `Step 3 Income Statement `; `S4` = `Step 4 Balance Sheet`; `S5` = `Step 5 Cash Flow Statement`; `S6` = `Step 6 DCF Valuation`; `S7` = `Step 7 Other Valuations+Compare`. S3 preserves the source sheet name's trailing space. Cell references explicitly include the sheet alias; narrative Rules references point to Step 1 drawing text.

### Reported financial inputs

| ID | Data item | Period / units | Workbook reference | Definition / requirement |
|---|---|---|---|---|
| F01 | Consolidated revenue | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S2!A9; S3!A8 | Reported company revenue; preserve gross/net and recognition basis |
| F02 | Revenue by business/product/service/geography | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S2!A7; S2!A13; S2!A18 | Amount plus disclosed segment/dimension identity; acquire all disclosed categories, not only two placeholders |
| F03 | Cost of revenue / COGS | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S3!A13 | Reported cost of goods/services/revenue, with the company definition |
| F04 | Sales and marketing expense | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S3!A19 | Separately disclosed sales/marketing expense; do not invent an SG&A split |
| F05 | Research and development expense | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S3!A25 | Reported R&D expense, separate from other operating expenses |
| F06 | General and administrative expense | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S3!A31 | Separately disclosed G&A; keep combined SG&A as a different concept when that is all reported |
| F07 | Depreciation expense | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S3!A37; S4!A20; S5!A9 | Depreciation, with amortization separated if reported; combined D&A is a different definition |
| F08 | Other income/expense, net | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S3!A50 | Signed non-operating amount and components; establish whether interest is included |
| F09 | Income tax provision / benefit | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S3!A54; S3!A55 | Reported historical tax expense/benefit; derive historical effective rate from reported pretax income |
| F10 | Net income / loss and common-shareholder numerator | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S3!A58; S5!A8 | Keep consolidated net income and income available to common shareholders distinct when they differ |
| F11 | Weighted-average shares: basic | Annual and standalone fiscal quarter; retain original YTD observations; shares | S3!A62; S3!C60 | Duration-weighted basic EPS denominator, not period-end outstanding shares |
| F12 | Weighted-average shares: diluted | Annual and standalone fiscal quarter; retain original YTD observations; shares | S3!A62; S3!C60 | Duration-weighted diluted EPS denominator; dilution definition must be selected for the model |
| F13 | Cash and cash equivalents | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A10; S5!A27; S5!A28; S5!A29 | Reported balance and opening cash; do not reconstruct first cash solely from simplified modeled flows |
| F14 | Short-term investments | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A11 | Reported current investment balance; distinguish restricted cash and securities classes |
| F15 | Accounts receivable, net | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A12; S5!A10 | Trade receivables after allowances; keep company-specific definition |
| F16 | Inventory | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A14; S5!A11 | Reported inventory when applicable; lack of inventory is not automatically missing data |
| F17 | Property, plant and equipment, net | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A18 | Reported net PP&E and opening balance; retain disposal/acquisition/FX effects when reconciling |
| F18 | Cash capital expenditures / PP&E purchases | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S4!A21; S5!A16 | Cash spent acquiring PP&E, distinct from PP&E balance changes, non-cash additions and acquisitions |
| F19 | Accounts payable | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A29; S5!A12 | Trade payable balance; separately identify accruals and other operating liabilities |
| F20 | Short-term borrowings | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A31; S6!D70 | Short-term debt; preserve components and avoid overlap with current maturities |
| F21 | Current maturities of long-term debt | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A31; S6!D70 | Current portion needed to define total short-term/current debt consistently |
| F22 | Long-term debt, non-current | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A34; S6!D70 | Reported non-current debt and composition; match measurement basis to debt bridge |
| F23 | Retained earnings / accumulated deficit | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A39 | Reported accumulated balance and opening balance, not simply sum of modeled net incomes |
| F24 | Common share capital: monetary book value | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A40; S5!A22 | Money recorded for common stock in equity; never map a share count into this row |
| F25 | Additional paid-in capital | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A41 | Reported equity balance; workbook row exists but its equity sum omits this row |

### Reported reconciliation additions

| ID | Data item | Period / units | Workbook reference | Definition / requirement |
|---|---|---|---|---|
| F26 | Reported gross profit | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S3!A15 | Compare with revenue minus cost of revenue |
| F27 | Reported operating expense total | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S3!A43 | Check presentation and avoid double-counting D&A inside COGS/SG&A |
| F28 | Reported operating income / loss | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S3!A46 | Validate modeled expense coverage and sign conventions |
| F29 | Reported income / loss before tax | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S3!A52; S3!A55 | Required denominator for observed effective tax rate |
| F30 | Reported basic EPS | Annual and standalone fiscal quarter; retain original YTD observations; currency/share | S3!A60 | Validate income numerator and weighted share denominator; retain reported rounding |
| F31 | Reported diluted EPS | Annual and standalone fiscal quarter; retain original YTD observations; currency/share | S3!A60 | Keep basic/diluted distinct; quarterly EPS is not safely summed to reproduce annual EPS |
| F32 | Reported current assets | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A16 | Validate that simplified workbook categories cover actual current assets |
| F33 | Reported non-current assets | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A24 | Include omitted intangibles/goodwill/other long-term assets as needed |
| F34 | Reported total assets | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A25; S4!A45 | Balance sheet reconciliation against reported liabilities and equity |
| F35 | Reported current liabilities | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A32 | Validate omitted accruals/deferred revenue/current liabilities |
| F36 | Reported non-current liabilities | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A35 | Validate omitted leases/deferred taxes/other long-term liabilities |
| F37 | Reported total liabilities | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A36; S4!A45 | Reconciliation total, with filing definition |
| F38 | Reported shareholders equity | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A42; S4!A45 | Include APIC, treasury stock, OCI and non-controlling interests according to reported definition |
| F39 | Reported liabilities plus equity | Fiscal quarter-end/year-end instant; opening balance before first modeled quarter; reported currency | S4!A44; S4!A45 | Independent check; do not force a balance by dropping categories |
| F40 | Reported cash from operating activities | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S5!A13; S5!B33 | Validate actual adjustments and working-capital changes; simplified model is not reported CFO |
| F41 | Reported cash from investing activities | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S5!A17 | Include actual investing activities beyond PP&E purchases |
| F42 | Reported cash from financing activities | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S5!A23 | Use cash transactions, not differences in monetary common stock/debt balances alone |
| F43 | Reported cash change and FX/restricted-cash bridge | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S5!A25; S5!A28; S5!A30 | Preserve separately reported cash change, FX effect and cash/restricted-cash definition |
| F44 | Cash borrowing, repayments, equity issuance, buybacks, dividends | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S5!A20; S5!A21; S5!A22; S5!A23 | Acquire separate transaction amounts when needed for cash flow reconciliation; do not net unrelated items |
| F45 | Other operating cash-flow adjustments | Annual and standalone fiscal quarter; retain original YTD observations; reported currency | S5!A9; S5!A10; S5!A11; S5!A12; S5!A13 | Acquire separately reported SBC, deferred tax, non-cash adjustments and other working-capital changes |

### Supplemental disclosures

| ID | Data item | Period / units | Workbook reference | Definition / requirement |
|---|---|---|---|---|
| S01 | Tax-loss carryforwards / NOL schedule | By jurisdiction, vintage and reporting date; reported currency | Rules note 8 | Amounts, jurisdiction, expiry, utilization limitations and tax-note evidence; do not assume losses directly equal a tax asset |
| S02 | Deferred revenue / contract liabilities | Period-end instant; reported currency | S4!A28 comment | Current/non-current balances and company definition, where material |
| S03 | Revenue operating drivers / company KPIs | Annual/quarter and company-defined KPI window; metric-specific | Rules important notes / note 21 | Disclosed volume, price, customers, subscribers, bookings or other applicable drivers; keep definitions/dimensions |
| S04 | Acquisition/disposal and segment-change evidence | Event date and impacted periods; metric-specific | Rules note 4 | Event dates, disclosed impacts and comparable revenue perimeter; distinguish organic from acquisition-driven growth |
| S05 | Company-issued guidance and supporting narrative | Publication date and target period; metric-specific | Rules notes 8,17,21 | Issuer-stated revenue, margins, capex, taxes or share guidance with target period, publication date and source; keep analyst assumptions separate |
| S06 | TAM / addressable-market evidence | As-of date and market scope; currency or units | Rules note 20 | Published size, market definition, geography, date, methodology and provenance; keep estimate distinct from reported company fact |
| S07 | Share splits, class changes and capital-action evidence | Event date and affected historical observations; share ratio, shares or reported currency | S3!A60; S3!A62; S4!A40; S7!I3 | Action type/date, split or class-conversion factor and reported EPS/share adjustment basis; preserve issuance/repurchase/dividend evidence separately |

### Market and valuation observations

| ID | Data item | Period / units | Workbook reference | Definition / requirement |
|---|---|---|---|---|
| M01 | Observed share price | Valuation timestamp; currency/share | S7!E3; S6!F28 | Price type, observation timestamp, currency, exchange and selected share class; IPO estimate must be tagged assumption |
| M02 | Actual shares outstanding by class | Shares as-of date; shares | S7!I3; S6!D72 | Point-in-time shares for market capitalization/equity per-share conversion; distinct from weighted-average and forecast EPS shares |
| M03 | Stock and benchmark adjusted-price history | Specified estimation window; currency/share or return | S6!F37; S6!F39 | Optional calibration inputs if beta/market returns are calculated; aligned returns, dates, adjustments and benchmark methodology |
| M04 | Observed risk-free benchmark yield | Valuation date; rate fraction | S6!F35 | Optional calibration for the assumed risk-free rate; currency, maturity, yield convention and as-of date |
| M05 | Interest expense/payments and debt pricing/terms | Reporting period / valuation date; reported currency / rate | S6!F46 | Optional calibration of pretax borrowing cost; keep expense, cash interest, coupons, maturities and measurement basis distinct |
| M06 | FX and quote-currency/scale conversion observations | Valuation timestamp, balance-sheet date or duration averaging window; currency/currency and quote scale | S7!E3; S7!I3; S2!A6; S3!A7 | Conditional rates and quote-unit conversion when reporting/model/price currencies differ; retain rate date, pair, source and chosen spot/average methodology |

### Versioned model assumptions

| ID | Data item | Period / units | Workbook reference | Definition / requirement |
|---|---|---|---|---|
| A01 | First forecast fiscal year | Forecast/valuation period plus scenario and approval version; fiscal year | S2!E4; S2!AE6 | Configurable anchor; source value 2024 is a template default, not a current-data fact |
| A02 | Revenue growth by line, period and scenario | Forecast/valuation period plus scenario and approval version; rate fraction | S2!AA14:AI14; S2!AA19:AI19 | Forecast the disclosed revenue lines using explicit assumptions; first forecast year has quarters and five-year horizon has annuals |
| A03 | Forecast COGS, S&M, R&D, G&A and depreciation ratios | Forecast/valuation period plus scenario and approval version; rate fraction | S3!AF14:AJ14; S3!AF20:AJ20; S3!AF26:AJ26; S3!AF32:AJ32; S3!AF38:AJ38 | Separate expense/revenue assumptions by field and period; account for industry presentation |
| A04 | Forecast effective tax and NOL utilization policy | Forecast/valuation period plus scenario and approval version; rate fraction / policy | S3!AB54:AJ55 | Forecast rate and loss-utilization logic; historical tax expense/rates remain acquired/derived observations |
| A05 | Forecast receivables, inventory and payables ratios | Forecast/valuation period plus scenario and approval version; rate fraction | S4!AA13:AI13; S4!AA15:AI15; S4!AA30:AI30 | Each ratio has explicit denominator (revenue versus COGS), period and scenario |
| A06 | Forecast capex / revenue | Forecast/valuation period plus scenario and approval version; rate fraction | S4!AA22:AI22 | Future capex assumption, distinct from reported cash purchases |
| A07 | Forecast short-term investments | Forecast/valuation period plus scenario and approval version; reported currency | S4!AA11:AI11 | Future balance/carry-forward choices are assumptions |
| A08 | Forecast short-/long-term debt and financing changes | Forecast/valuation period plus scenario and approval version; reported currency | S4!AA31:AI31; S4!AA34:AI34 | Period/scenario balances and cash financing policy; not observed future facts |
| A09 | Forecast EPS/valuation share counts and dilution | Forecast/valuation period plus scenario and approval version; shares | S3!AB62:AJ62 | Selected share definition, issuance/repurchase/dilution assumptions and as-of policy |
| A10 | Target equity/debt weights | Forecast/valuation period plus scenario and approval version; rate fraction | S6!G23; S6!G25 | Equity weight is entered; debt weight is its complement; version assumed versus observed weights |
| A11 | Assumed risk-free rate | Forecast/valuation period plus scenario and approval version; rate fraction | S6!F35 | Model discount input with currency/maturity/as-of and rationale, even if calibrated from an observation |
| A12 | Assumed beta | Forecast/valuation period plus scenario and approval version; dimensionless | S6!F37 | Model input with benchmark/window/method or explicit analyst assumption |
| A13 | Assumed market return | Forecast/valuation period plus scenario and approval version; rate fraction | S6!F39 | Expected market return and methodology; not an SEC reported fact |
| A14 | Assumed pretax cost of debt | Forecast/valuation period plus scenario and approval version; rate fraction | S6!F46 | Entered model borrowing-cost input; after-tax cost is calculated |
| A15 | Terminal growth rate | Forecast/valuation period plus scenario and approval version; rate fraction | S6!F62 | Long-run model assumption, separate from historical growth observations |
| A16 | Bull/base/bear revenue multiples and PEG policies | Forecast/valuation period plus scenario and approval version; multiple | S7!C13; S7!C17; S7!C21; S7!K14; S7!K18; S7!K22 | Revenue multiples are blue inputs; PEG factors 2/1/1.5 are embedded formula assumptions |
| A17 | Investor required return / discount input | Forecast/valuation period plus scenario and approval version; rate fraction | S7!I4; S7!D24; S7!K24 | User-specific discount input used to discount valuation comparisons |
| A18 | Forecast monetary common share capital and APIC | Forecast/valuation period plus scenario and approval version; reported currency | S4!AA40:AI40; S4!AA41:AI41 | Assume future monetary common-stock and additional-paid-in-capital balances or changes separately from EPS share counts and actual cash equity proceeds. |
| A19 | Forecast other income / expense, net | Forecast/valuation period plus scenario and approval version; reported currency | S3!AB50:AJ50 | Scenario-specific forecast signed non-operating income/expense; do not treat the template zero defaults as observed facts. |

### Computed outputs

| ID | Data item | Period / units | Workbook reference | Definition / requirement |
|---|---|---|---|---|
| D01 | Revenue sum of mapped lines | Matching fiscal period or scenario; Output-specific | S2!A9; S3!A8 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D02 | YoY/QoQ growth | Matching fiscal period or scenario; Output-specific | S2!A10; S2!A11; S2!A14; S2!A15; S2!A19; S2!A20; S3!A9; S3!A10; S3!A21; S3!A22; S3!A27; S3!A28; S3!A33; S3!A34; S3!A39; S3!A40; S3!A45; S3!A61; S3!A65 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D03 | Revenue line mix / seasonality | Matching fiscal period or scenario; Output-specific | S2!A12; S2!A16; S2!A17; S2!A21; S2!A22 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D04 | Gross profit and gross margin | Matching fiscal period or scenario; Output-specific | S3!A15; S3!A16 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D05 | Expense and other-income ratios | Matching fiscal period or scenario; Output-specific | S3!A14; S3!A20; S3!A26; S3!A32; S3!A38; S3!A44; S3!A51 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D06 | Modeled total expenses | Matching fiscal period or scenario; Output-specific | S3!A43 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D07 | Modeled operating income and margin | Matching fiscal period or scenario; Output-specific | S3!A46; S3!A47 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D08 | Template EBITDA and margin | Matching fiscal period or scenario; Output-specific | S3!A48; S3!A49 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D09 | Modeled pretax income, tax, net income and margins | Matching fiscal period or scenario; Output-specific | S3!A52; S3!A53; S3!A54; S3!A55; S3!A58; S3!A59 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D10 | Modeled GAAP EPS | Matching fiscal period or scenario; Output-specific | S3!A60 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D11 | Template depreciation-adjusted EPS | Matching fiscal period or scenario; Output-specific | S3!A64 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D12 | Modeled asset/liability/equity totals and reconciliation | Matching fiscal period or scenario; Output-specific | S4!A16; S4!A24; S4!A25; S4!A32; S4!A35; S4!A36; S4!A42; S4!A44; S4!A45 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D13 | AR/inventory/AP and capex ratios | Matching fiscal period or scenario; Output-specific | S4!A13; S4!A15; S4!A22; S4!A30 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D14 | Cash, equipment and retained-earnings roll-forwards | Matching fiscal period or scenario; Output-specific | S4!A10; S4!A18; S4!A20; S4!A39 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D15 | Modeled working-capital/debt/equity cash-flow changes | Matching fiscal period or scenario; Output-specific | S5!A10; S5!A11; S5!A12; S5!A20; S5!A21; S5!A22 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D16 | Modeled CFO/CFI/CFF and cash reconciliation | Matching fiscal period or scenario; Output-specific | S5!A8; S5!A9; S5!A13; S5!A16; S5!A17; S5!A23; S5!A25; S5!A27; S5!A28; S5!A29; S5!A30 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D17 | Template FCF = modeled CFO minus cash capex | Matching fiscal period or scenario; Output-specific | S5!A32; S5!B33; S5!F33; S5!AE33; S5!AF33; S6!C11:G11 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D18 | Cost of equity, after-tax debt cost and WACC | Matching fiscal period or scenario; Output-specific | S6!C23; S6!C25; S6!C27; S6!C39; S6!C48; S6!F48 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D19 | PV of forecast FCF, terminal value, equity bridge and per-share DCF | Matching fiscal period or scenario; Output-specific | S6!D55; S6!D61; S6!D62; S6!D63; S6!D69; S6!D70; S6!D71; S6!D72; S6!D73 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D20 | DCF sensitivity to growth and WACC | Matching fiscal period or scenario; Output-specific | S6!D78:I85 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D21 | Implied market cap from price and selected share count | Matching fiscal period or scenario; Output-specific | S7!I3; S6!F27 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D22 | P/revenue price targets and implied target capitalization | Matching fiscal period or scenario; Output-specific | S7!D14:H24 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D23 | Growth-based P/E/PEG price targets and target capitalization | Matching fiscal period or scenario; Output-specific | S7!K9:O24 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |
| D24 | DCF/P-revenue/P-E scenario comparisons, average and percentage-to-target | Matching fiscal period or scenario; Output-specific | S7!C27:E35 | Compute from acquired observations and approved assumptions; retain reported equivalents separately where available |

### Context and provenance

| ID | Data item | Period / units | Workbook reference | Definition / requirement |
|---|---|---|---|---|
| P01 | Company/CIK and security/share-class mapping | Every observation or derived/model record; typed metadata | Not a single workbook cell | Use existing MDM identity, company name, CIK, ticker, exchange and share class; security prices are not keyed by company name alone; retain industry/SIC and reporting basis where available for industry-specific mappings. |
| P02 | Fiscal calendar and period identity | Every observation or derived/model record; typed metadata | Not a single workbook cell | Fiscal year-end, fiscal year/quarter, actual period dates and duration; calendar labels alone are insufficient |
| P03 | Instant/duration/YTD context | Every observation or derived/model record; typed metadata | Not a single workbook cell | Preserve start/end or instant date and standalone-versus-YTD indication; share averages and ratios are not additive flows |
| P04 | Filing and disclosure identity | Every observation or derived/model record; typed metadata | Not a single workbook cell | Accession, form (including amendments), document/URL and reporting-period association |
| P05 | Filing/publication availability date | Every observation or derived/model record; typed metadata | Not a single workbook cell | Preserve filing/publication date; acceptance timestamp when available from source metadata; retain comparative/restated vintages |
| P06 | Taxonomy and raw concept | Every observation or derived/model record; typed metadata | Not a single workbook cell | Namespace/version, tag, reported label/definition and original custom concept when applicable |
| P07 | Segment/dimension/context members | Every observation or derived/model record; typed metadata | Not a single workbook cell | Keep axes/members, geography, product, segment and entity-scope; version renamed categories |
| P08 | Units, reporting currency and display scale | Every observation or derived/model record; typed metadata | Not a single workbook cell | Preserve raw unit/value; normalize currency amounts and share counts for workbook thousands; per-share values remain per-share |
| P09 | Precision and sign conventions | Every observation or derived/model record; typed metadata | Not a single workbook cell | Preserve numeric precision; filing decimals/scale/sign if present; distinguish expenses, benefits and cash payments consistently |
| P10 | Immutable capture provenance | Every observation or derived/model record; typed metadata | Not a single workbook cell | Source artifact URI/key, SHA256, captured-at time, producer and configured source version |
| P11 | Concept mapping and transformation lineage | Every observation or derived/model record; typed metadata | Not a single workbook cell | Approved mapping version, raw inputs, conversion/aggregation/quarter derivation and output hashes |
| P12 | Missing/unreported/zero/non-applicable status | Every observation or derived/model record; typed metadata | Not a single workbook cell | Template zeros/N/A are placeholders; acquire actual values without treating absent facts as zero; retain validation/defer reasons |
| P13 | Valuation and knowledge cutoffs | Every observation or derived/model record; typed metadata | Not a single workbook cell | Price observation date, shares measurement date, last available filing and as-of selection policy |
| P14 | Model/assumption definitions and scenario | Every observation or derived/model record; typed metadata | Not a single workbook cell | Approval/version, scenario, time horizon, EPS basis, cash-flow definition, discount timing and currencies |

## Deliverables

- `DATA-REQUIREMENTS.csv` and `DATA-REQUIREMENTS.json`: complete definitions, source routes, priorities and notes.
- `Fundamentals-Acquisition-Requirements.xlsx`: the same catalog grouped into tabs, with model gaps and reading guidance.
- `GAPS.json`: fourteen workbook ambiguities to resolve before implementation.
- `EVIDENCE.json`: source hash, inspection counts and verification results.
- `HANDOFF-TO-CLAUDE.md`: scope and next planning steps.
