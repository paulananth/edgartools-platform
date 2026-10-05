# Trial B answer key: Contoso V2, 10k build

Written 2026-10-05, **before the data-profiling skill or its helpers exist**
(plan decision 35). The commit that adds this file is the proof: it comes
before any commit under `skills/data-profiling/`. Sources: the column headers of
the 8 CSV files, and the published Contoso V2 data model (sql-bi,
Contoso-Data-Generator-V2, MIT). No profiling result was used.

The skill never reads this folder. Trial B runs twice: once on the CSV files,
once on a SQLite database built from them by `build_sqlite.py` (outside the
skill). Both runs must give the same findings.

## How a run is scored

A run **matches** when every line below holds. Field names are the
`findings.yaml` names (`docs/specs/profiling/findings.md`).

| Item | Match rule |
|---|---|
| `class` | equal to the expected class, or to a listed alternative |
| `record_key.columns` | the same set of columns |
| relationship | found with the same `from` and `to` columns, `inclusion` ≥ 0.9, the same `cardinality` |
| hierarchy | found on the named part, with an `evidence_kind` from the allowed set |
| `sensitivity` | every listed column tagged `personal` or `sensitive_personal`; no column of a non-person part tagged personal |
| `time` | the listed roles found on the listed columns |
| `confidence` | ≥ 0.6 for the expected class |
| `code_lists` | every listed column reported as a code list (more are allowed) |

A miss is reported line by line in `RESULT.md`; nothing is tuned to pass.

## Parts

| Part | Class | Alternative | Record key | Why |
|---|---|---|---|---|
| customer | master | — | `CustomerKey` | people buying; names, address, birthday; pointed at by orders and sales |
| product | master | — | `ProductKey` | things sold; name, brand, issued code; pointed at by order rows and sales |
| store | master | — | `StoreKey` | places selling; issued code, open and close dates; pointed at by orders and sales |
| date | reference | — | `Date` | a calendar: fixed set of values that give dates their meaning (year, quarter, month, working day) |
| currencyexchange | transaction | reference | (`Date`, `FromCurrency`, `ToCurrency`) | a daily time series of rates; a rate table is also defensible as reference |
| orders | transaction | — | `OrderKey` | one event per order; the largest growth, links to three masters |
| orderrows | transaction | — | (`OrderKey`, `LineNumber`) | the lines of an order |
| sales | transaction | — | (`OrderKey`, `LineNumber`) | orders and their lines, joined into one wide table |

No part is a relationship (link) table, and no part is metadata.

## Identifiers (other than the record key)

| Part | Column | Proposal |
|---|---|---|
| product | `ProductCode` | unique; `cross_reference` or `none` (a second local code) |
| store | `StoreCode` | unique; `cross_reference` or `none` |

## Relationships

| From | To | Cardinality |
|---|---|---|
| orders.`CustomerKey` | customer.`CustomerKey` | N:1 |
| orders.`StoreKey` | store.`StoreKey` | N:1 |
| orders.`OrderDate` | date.`Date` | N:1 |
| orderrows.`OrderKey` | orders.`OrderKey` | N:1 |
| orderrows.`ProductKey` | product.`ProductKey` | N:1 |
| sales.`CustomerKey` | customer.`CustomerKey` | N:1 |
| sales.`StoreKey` | store.`StoreKey` | N:1 |
| sales.`ProductKey` | product.`ProductKey` | N:1 |
| sales.(`OrderKey`, `LineNumber`) | orderrows.(`OrderKey`, `LineNumber`) | 1:1 |

`onboard` for every relationship above: `separate` (they belong to transaction
parts, onboarded after the masters).

## Hierarchies

| Part | Hierarchy | Type | Allowed evidence kinds |
|---|---|---|---|
| product | `SubCategoryKey` → `CategoryKey` (product category) | reference | functional_dependency, code_nesting |
| date | `Date` → `YearMonth` → `YearQuarter` → `Year` | reference | functional_dependency |

Customer and store geography (`State` → `Country` → `Continent`) is
**optional**: found or not, it does not fail the run.

## Code lists (embedded in other parts)

| Part | Columns |
|---|---|
| customer | `Continent`, `Country` (label `CountryFull`), `State` (label `StateFull`), `Gender`, `Title` |
| product | `CategoryKey` (label `CategoryName`), `SubCategoryKey` (label `SubCategoryName`), `Brand`, `Manufacturer`, `Color`, `WeightUnit` |
| store | `CountryCode` (label `CountryName`), `Status` |
| orders | `CurrencyCode` |
| currencyexchange | `FromCurrency`, `ToCurrency` |

## Sensitivity

customer: `GivenName`, `MiddleInitial`, `Surname`, `StreetAddress`, `ZipCode`,
`Birthday`, `Age`, `Latitude`, `Longitude` are personal (or sensitive
personal). No column of product, store, date, currencyexchange, orders,
orderrows or sales is tagged personal.

## Time

| Part | Role | Column |
|---|---|---|
| customer | as_of (valid from / to) | `StartDT`, `EndDT` |
| orders | event_time | `OrderDate` |
| sales | event_time | `OrderDate` |
| currencyexchange | series | key (`FromCurrency`, `ToCurrency`), time `Date`, step 1 day |

`delivery` is `unknown` for every part (one delivery only).
