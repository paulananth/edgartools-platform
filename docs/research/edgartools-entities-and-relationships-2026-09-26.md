# edgartools 5.30.0 entities and relationships

Checked the installed package at `.venv/.../edgar`, version `5.30.0` in `__about__.py`. edgartools does not store a relationship graph. It parses a filing into parties and facts. This platform's MDM turns some of those facts into edges.

## Entities

| Class | Module | What it is | Identity |
| --- | --- | --- | --- |
| `SecFiler` | `entity/core.py` | Abstract filer. Must have a CIK, filings, and facts. | CIK |
| `Entity` | `entity/core.py` | Any SEC filer. `get_entity` returns this. | CIK, or a ticker resolved to a CIK |
| `Company` | `entity/core.py` | A public company. `get_company`. | CIK or ticker |
| `FundCompany` | `funds/core.py` | A fund registrant. Subclass of `Entity`. The package text calls it the legal entity that files, and gives "Vanguard" as the example. | CIK |
| `FundSeries` | `funds/core.py` | One product under that registrant. | Series id |
| `FundClass` | `funds/core.py` | One share class. | Class id or ticker |
| `Person` | `_party.py` | A first and last name on a form, plus an address. Not an `Entity`. No CIK. | The name on that form |
| `Issuer` | `_party.py` | A Form D style issuer: CIK, legal name, previous names, entity type, jurisdiction. | CIK |

There is no Security class, no Adviser class, and no GLEIF type. A security is a row on a filing. An adviser is a service-provider row on N-CEN or a CRD on an ADV filing this platform parses itself.

## Relationships that are explicit in a filing

| Filing object | Where | What it links |
| --- | --- | --- |
| `ReportingRelationship` | `ownership/ownershipforms.py` | The reporting owner to the issuer: director, officer, ten percent owner, other, and officer title. Forms 3, 4, and 5. |
| `DerivativeHoldings` / `NonDerivativeHoldings` | same | That owner and a security title, with shares. No CUSIP. |
| Information-table row | `thirteenf` | Issuer name, class title, CUSIP, shares, value. The filer is the manager. |
| `IssuerInfo` / `SecurityInfo` | `beneficial_ownership/models.py` | Schedule 13D/13G subject company (CIK, name, CUSIP) and the class (title, CUSIP). |
| `InvestmentOrSecurity` | `funds/reports.py` | An N-PORT holding: name, LEI, title, CUSIP, other identifiers, units, value. |
| `PortfolioSecurity` | `funds/nmfp3.py` | An N-MFP holding: issuer, CUSIP, ISIN. |
| `FundSeriesInfo` plus service providers | `funds/ncen.py` | A series (name, series id, LEI) and its investment advisers, directors, accountant, and ETF authorized participants. |
| `Holding` | `funds/ncsr.py` | A holding named on an N-CSR. |

`ReportingRelationship` is the only type whose name says relationship. The others are nested records. None of them is `ISSUED_BY`, `MANAGES_FUND`, `IS_ENTITY_OF`, or `IS_PERSON_OF`. Those names belong to this platform.

## What this platform does with them

The warehouse calls edgartools for the 13F information table and for Forms 3, 4, and 5 names. ADV bulk is parsed here, not by an edgartools entity class: adviser CRD and private-fund id, no CUSIP. N-PORT and N-CEN exist in the library and are not ingested. The only N-PORT use in the repo is `scripts/batch/batch_NPORTP.py`, which prints a sample.
