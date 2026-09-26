# Company mastering does not collapse a fund trust into its sponsor

Date: 2026-09-25

Question: does company mastering treat `ISHARES TR`, `VANGUARD INDEX FDS`,
and `SPDR S&P 500 ETF TR` as BlackRock, Vanguard, and SSGA?

## What company mastering actually joins

A Company is keyed by CIK. The old resolver says CIK is definitive and a
fuzzy name match is rarely needed (`edgar_warehouse/mdm/resolvers/company.py`).
The accepted Company policy joins that CIK to a GLEIF LEI. A name change
alone does not split the Company or suspend the link
(`docs/specs/clean-mdm/company-policy.md`, Q9). Two published Companies
are not consolidated on a fuzzy name
(`company-policy.md`, Q10; `docs/specs/clean-mdm/company-completion.md`,
item 4: no name-only automatic rule).

A 13F issuer string is not an input. Company mastering reads `sec_company`,
which is the SEC registrant, not the `nameOfIssuer` on an information table.

## What that confirms

`GOOGLE INC` and `ALPHABET INC` are one Company when they are one CIK that
renamed. Company mastering does confirm that case. The filed spelling stays
an alias.

`ISHARES TR`, `VANGUARD INDEX FDS`, and `SPDR S&P 500 ETF TR` are the names
on the 13F rows. They are not the legal names BlackRock, Vanguard, and SSGA.
Nothing in company mastering joins a product trust to its sponsor by those
strings. If the trust has its own CIK, it is a separate Company.

## Consequence for ISSUED_BY

Pointing the ETF CUSIP at BlackRock, Vanguard, or SSGA is a new sponsor
relationship. It is not a result company mastering already produces.
