# Trial A answer key: SEC submissions and GLEIF golden copies

Written 2026-10-05, **before the data-profiling skill or its helpers exist**.
Sources: the record structure of one file of each input, the providers'
published file descriptions, and what this repo already masters. No profiling
result was used. The skill never reads this folder. No request to any provider:
local copies only.

Scoring is the same as Trial B ([B/ANSWER-KEY.md](../B/ANSWER-KEY.md), "How a
run is scored"). Column names below are flattened paths (`a.b.c`); a
`{"$": value}` wrapper reads as its value.

## Inputs

| Input | Location (local) | Size | Scan |
|---|---|---|---|
| submissions | `~/.local/share/edgartools/clean-mdm/captures/sec.submissions.company/all-76230/bronze/submissions/` (one JSON per entity) | ~1.5 GB, 76k files | full |
| tickers | `.../all-76230/bronze/reference/sec/company_tickers_exchange/` | small | full |
| lei2 | `~/.local/share/edgartools/clean-mdm/research/gleif-20260911-1600/*lei2*.zip` | 13.25 GB unzipped | **sampled**, then full passes for key candidates |
| rr | `.../*rr*.zip` | 1.12 GB unzipped | full |
| repex | `.../*repex*.zip` | 1.55 GB unzipped | full |

## Parts

| Part | Class | Alternative | Record key | Why |
|---|---|---|---|---|
| submissions | master | — | `cik` | one entity per file; names, addresses, issued identifiers |
| submissions.tickers / exchanges (parallel lists) | reference | master | (`cik`, position) | listings of an entity; small code lists |
| submissions.formerNames | metadata | master | (`cik`, position) or (`cik`, `name`, `from`) | name history of the parent |
| submissions.filings.recent (object of equal-length lists) | transaction | — | `accessionNumber` | one row per filing event |
| submissions.filings.files | metadata | — | `name` | pointers to further pages of the same data |
| tickers | master | reference | `ticker` | listings: ticker to entity |
| lei2 | master | — | `LEI` | one legal entity per record; names, addresses, issued identifier |
| lei2 other-name lists | metadata | master | (`LEI`, position) | name history and translations of the parent |
| rr | relationship | — | (`StartNode.NodeID`, `EndNode.NodeID`, `RelationshipType`) | links between two lei2 records with a role and periods |
| repex | metadata | transaction, unknown | (`LEI`, `ExceptionCategory`) + any extra column needed | why a parent is not reported; facts about a lei2 record |

## Identifiers

| Part | Column | Expected finding |
|---|---|---|
| lei2 | `LEI` | fixed length 20, one shape, check digit family **mod 97-10**, pass rate ≥ 0.99 and ≥ 5× chance |
| submissions | `cik` | digits only, unique; no check digit family above chance |
| submissions | `ein` | fixed length 9, digits; `cross_reference` |
| submissions | `lei` | mostly empty; when present, same shape and family as lei2.`LEI`; `cross_reference` |
| filings.recent | `accessionNumber` | one fixed shape (`9999999999-99-999999`), unique |

## Relationships

| From | To | Cardinality | onboard |
|---|---|---|---|
| rr.`StartNode.NodeID` | lei2.`LEI` | N:1 | together |
| rr.`EndNode.NodeID` | lei2.`LEI` | N:1 | together |
| repex.`LEI` | lei2.`LEI` | N:1 | separate or together |
| tickers.`cik` | submissions.`cik` | N:1 | together or separate |
| filings.recent → submissions (parent) | submissions.`cik` | N:1 | separate |

rr's minimal key is made only of keys to lei2 plus a role column
(`RelationshipType`), so rr must be classed as a relationship (link) part, with
`role_column` = `RelationshipType`.

## Hierarchies

| Part | Type | Allowed evidence kinds |
|---|---|---|
| rr over lei2 (parent links between legal entities) | master_data | parent_column |

A reference hierarchy over `sic` codes is **optional** (code nesting).

## Code lists

| Part | Columns (at least) |
|---|---|
| submissions | `entityType`, `sic` (label `sicDescription`), `stateOfIncorporation` (label `stateOfIncorporationDescription`), `category` |
| filings.recent | `form`, `act` |
| tickers | `exchange` |
| lei2 | `Entity.LegalJurisdiction`, `Entity.EntityCategory`, `Entity.EntityStatus`, `Registration.RegistrationStatus`, `Entity.LegalForm.EntityLegalFormCode` |
| rr | `RelationshipType` |
| repex | `ExceptionCategory`, `ExceptionReason` |

## Sensitivity

No GLEIF column is personal. Submissions describe filers, some of them people:
no requirement either way, and the result is reported, not scored.

## Time

| Part | Role | Column |
|---|---|---|
| lei2 | as_at | `Registration.LastUpdateDate` |
| filings.recent | event_time | `filingDate` or `acceptanceDateTime` |
| rr | valid from / to | the relationship period start and end dates |

## Scale

lei2 is over 5 GB: the run must say so, state its time estimate before the
full passes, record `scan: sampled` with its seed, and confirm `LEI`
uniqueness with a full pass. No input is unzipped to disk in full.
