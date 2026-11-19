# Company mastering does not collapse a fund trust into its sponsor

Date: 2026-09-25

Question: does company mastering treat an ETF trust named on 13F rows (`EXAMPLE INDEX TR`, say)
as the sponsor that runs it?

## What company mastering actually joins

A Company is keyed by CIK. The old resolver says CIK is definitive and a
fuzzy name match is rarely needed (`edgar_warehouse/mdm/resolvers/company.py`).
The accepted Company policy joins that CIK to a GLEIF LEI. A name change
alone does not split the Company or suspend the link
(`docs/specs/mdm/company-policy.md`, Q9). Two published Companies
are not consolidated on a fuzzy name
(`company-policy.md`, Q10; `docs/specs/mdm/company-completion.md`,
item 4: no name-only automatic rule).

A 13F issuer string is not an input. Company mastering reads `sec_company`,
which is the SEC registrant, not the `nameOfIssuer` on an information table.

## What that confirms

`GOOGLE INC` and `ALPHABET INC` are one Company when they are one CIK that
renamed. Company mastering does confirm that case. The filed spelling stays
an alias.

The trusts' names are what the 13F rows carry.
They are not the sponsors' legal names.
Nothing in company mastering joins a product trust to its sponsor by those
strings. If the trust has its own CIK, it is a separate Company.

## Consequence for ISSUED_BY

Pointing the ETF CUSIP at the sponsor is a new sponsor
relationship. It is not a result company mastering already produces.
