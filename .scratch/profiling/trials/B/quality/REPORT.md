# Profiling report: None

Profiled 2026-10-05T21:28:51-04:00 by data-profiling 1. Scan: **full**; 14.3 s. Approval: **draft**.

## Parts

| Part | Rows | Class | Confidence | Record key | Store (advice) |
|---|---|---|---|---|---|
| currencyexchange | 36525 | transaction | 1.0 | Date, FromCurrency, ToCurrency | silver |
| customer | 104990 | master | 0.833 | CustomerKey | mdm |
| date | 1461 | reference | 0.857 | Date | rdm |
| orderrows | 7794 | transaction | 1.0 | OrderKey, LineNumber | silver |
| orders | 3242 | transaction | 0.833 | OrderKey | silver |
| product | 2517 | master | 1.0 | ProductKey | mdm |
| sales | 7794 | transaction | 0.833 | OrderKey, LineNumber | silver |
| store | 74 | master | 1.0 | StoreKey | mdm |

## Why each class

- **currencyexchange** is transaction: has a unique key (required); points at other parts; points at as many parts as point at it; has an event time or measures; no name-like text; at least as large as the parts it points at.
- **customer** is master: has a unique key (required); other parts point at it; points at few parts; has name-like text; has attributes besides codes and dates. Failed: smaller than the parts pointing at it.
- **date** is reference: has a unique key (required); other parts point at it; at most 10000 rows; points at no other part (required); no name-like text besides labels; codes with label columns. Failed: only codes, labels and dates.
- **orderrows** is transaction: has a unique key (required); points at other parts; points at as many parts as point at it; has an event time or measures; no name-like text; at least as large as the parts it points at.
- **orders** is transaction: has a unique key (required); points at other parts; points at as many parts as point at it; has an event time or measures; no name-like text. Failed: at least as large as the parts it points at.
- **product** is master: has a unique key (required); other parts point at it; points at few parts; has name-like text; smaller than the parts pointing at it; has attributes besides codes and dates.
- **sales** is transaction: has a unique key (required); points at other parts; points at as many parts as point at it; has an event time or measures; no name-like text. Failed: at least as large as the parts it points at.
- **store** is master: has a unique key (required); other parts point at it; points at few parts; has name-like text; smaller than the parts pointing at it; has attributes besides codes and dates.

## Relationships

| From | To | Inclusion | Cardinality | Onboard | Why |
|---|---|---|---|---|---|
| currencyexchange.Date | date.Date | 1.0 | N:1 | separate | a transaction part pointing at a reference part: onboarded after it |
| orderrows.OrderKey | orders.OrderKey | 1.0 | N:1 | separate | a transaction part pointing at a transaction part: onboarded after it |
| orderrows.ProductKey | product.ProductKey | 1.0 | N:1 | separate | a transaction part pointing at a master part: onboarded after it |
| orders.CustomerKey | customer.CustomerKey | 1.0 | N:1 | separate | a transaction part pointing at a master part: onboarded after it |
| orders.DeliveryDate | date.Date | 1.0 | N:1 | separate | a transaction part pointing at a reference part: onboarded after it |
| orders.OrderDate | date.Date | 1.0 | N:1 | separate | a transaction part pointing at a reference part: onboarded after it |
| orders.StoreKey | store.StoreKey | 1.0 | N:1 | separate | a transaction part pointing at a master part: onboarded after it |
| sales.CustomerKey | customer.CustomerKey | 1.0 | N:1 | separate | a transaction part pointing at a master part: onboarded after it |
| sales.DeliveryDate | date.Date | 1.0 | N:1 | separate | a transaction part pointing at a reference part: onboarded after it |
| sales.OrderDate | date.Date | 1.0 | N:1 | separate | a transaction part pointing at a reference part: onboarded after it |
| sales.OrderKey | orders.OrderKey | 1.0 | N:1 | separate | a transaction part pointing at a transaction part: onboarded after it |
| sales.ProductKey | product.ProductKey | 1.0 | N:1 | separate | a transaction part pointing at a master part: onboarded after it |
| sales.StoreKey | store.StoreKey | 1.0 | N:1 | separate | a transaction part pointing at a master part: onboarded after it |
| sales.OrderKey, LineNumber | orderrows.OrderKey, LineNumber | 1.0 | 1:1 | separate | a transaction part pointing at a transaction part: onboarded after it |
| orderrows.OrderKey, LineNumber | sales.OrderKey, LineNumber | 1.0 | 1:1 | separate | a transaction part pointing at a transaction part: onboarded after it |

## Hierarchies

- **customer: State > GeoAreaKey > StateFull** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 0.999962, depth 3, balanced, orphans 0, cycles 0, invalid rows 4.
- **customer: Continent > Country** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 1.0, depth 2, balanced, orphans 0, cycles 0, invalid rows 0.
- **date: Year > YearQuarter > YearMonth** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 1.0, depth 3, balanced, orphans 0, cycles 0, invalid rows 0.
- **date: Quarter > Month** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 1.0, depth 2, balanced, orphans 0, cycles 0, invalid rows 0.
- **product: CategoryKey > SubCategoryKey** (reference, code_nesting): each code starts with its parent's code; holds 1.0, depth 2, balanced, orphans 0, cycles 0, invalid rows 0.
- **product: Manufacturer > Brand** (reference, functional_dependency): each value of a level has one value at the next coarser level; holds 1.0, depth 2, balanced, orphans 0, cycles 0, invalid rows 0.

## Identifiers, sensitive columns and time

- **currencyexchange**: identifiers: Date (record_key), FromCurrency (record_key), ToCurrency (record_key); event Date, series by FromCurrency, ToCurrency every 1 day
- **customer**: identifiers: CustomerKey (record_key); sensitive: Gender (personal), Title (personal), GivenName (personal), MiddleInitial (personal), Surname (personal), StreetAddress (personal), ZipCode (personal), Birthday (personal), Age (personal), Latitude (personal), Longitude (personal); as of StartDT–EndDT
- **date**: identifiers: Date (record_key), DateKey (cross_reference), YearMonthNumber (none); series by  every 1 day
- **orderrows**: identifiers: OrderKey (record_key), LineNumber (record_key)
- **orders**: identifiers: OrderKey (record_key); event OrderDate
- **product**: identifiers: ProductKey (record_key), ProductCode (cross_reference), SubCategoryKey (none)
- **sales**: identifiers: OrderKey (record_key), LineNumber (record_key); event OrderDate
- **store**: identifiers: StoreKey (record_key); as of OpenDate–CloseDate

## Data quality to hand to data-quality

- customer: placeholder: a stand-in for no value, which must not match or merge
- customer: placeholder: a stand-in for no value, which must not match or merge
- customer: shape_outlier: 99.88% of values share one shape; these do not
- customer: code_list: 3 codes in this delivery; a new code is flagged until the code set has it
- customer: code_list: 8 codes in this delivery; a new code is flagged until the code set has it
- customer: hierarchy_invalid: rows that break the rule 'each value of a level has one value at the next coarser level'
- date: code_list: 4 codes in this delivery; a new code is flagged until the code set has it
- date: code_list: 16 codes in this delivery; a new code is flagged until the code set has it
- date: code_list: 4 codes in this delivery; a new code is flagged until the code set has it
- date: code_list: 48 codes in this delivery; a new code is flagged until the code set has it
- date: code_list: 48 codes in this delivery; a new code is flagged until the code set has it
- date: code_list: 12 codes in this delivery; a new code is flagged until the code set has it
- date: code_list: 12 codes in this delivery; a new code is flagged until the code set has it
- date: code_list: 7 codes in this delivery; a new code is flagged until the code set has it
- date: code_list: 7 codes in this delivery; a new code is flagged until the code set has it
- date: code_list: 2 codes in this delivery; a new code is flagged until the code set has it
- orderrows: code_list: 10 codes in this delivery; a new code is flagged until the code set has it
- orders: code_list: 5 codes in this delivery; a new code is flagged until the code set has it
- product: code_list: 11 codes in this delivery; a new code is flagged until the code set has it
- product: code_list: 15 codes in this delivery; a new code is flagged until the code set has it
- product: code_list: 17 codes in this delivery; a new code is flagged until the code set has it
- product: code_list: 3 codes in this delivery; a new code is flagged until the code set has it
- product: code_list: 8 codes in this delivery; a new code is flagged until the code set has it
- product: code_list: 32 codes in this delivery; a new code is flagged until the code set has it
- sales: code_list: 10 codes in this delivery; a new code is flagged until the code set has it
- sales: code_list: 5 codes in this delivery; a new code is flagged until the code set has it
- store: code_list: 9 codes in this delivery; a new code is flagged until the code set has it
- store: code_list: 39 codes in this delivery; a new code is flagged until the code set has it
- store: code_list: 2 codes in this delivery; a new code is flagged until the code set has it

## Questions for the operator (one at a time)

1. Is customer a new master kind named 'customer'? Recommendation: yes: has a unique key (required); other parts point at it; points at few parts; has name-like text; has attributes besides codes and dates
2. Is product a new master kind named 'product'? Recommendation: yes: has a unique key (required); other parts point at it; points at few parts; has name-like text; smaller than the parts pointing at it; has attributes besides codes and dates
3. Is store a new master kind named 'store'? Recommendation: yes: has a unique key (required); other parts point at it; points at few parts; has name-like text; smaller than the parts pointing at it; has attributes besides codes and dates

Samples of personal columns are masked to their shape. Store suggestions are advice only.
