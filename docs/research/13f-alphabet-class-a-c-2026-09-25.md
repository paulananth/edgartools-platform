# Alphabet Class A and Class C on 13F information tables

Date: 2026-09-25
Source: the 1,000 largest pinned information tables in
`heavy-parse-s3-pin-13f-2026-09-25.json`, read from the local ETag cache.
No SEC request. Each `infoTable` contributed `nameOfIssuer`, `titleOfClass`,
and `cusip`.

992 of the 1,000 files contain at least one Alphabet or legacy Google row.
Those rows use 132 distinct issuer/title/CUSIP spellings.

## Two CUSIPs, one issuer

| CUSIP | What the filings call it | Rows in this pin |
| --- | --- | ---: |
| `02079K305` | Class A. The common title is `CAP STK CL A` with issuer `ALPHABET INC` (2,679 rows). The same CUSIP is also titled `COM`, `Stock`, `COMMON STOCK`, `EQUITY`, and `CL A`. | about 3,100 |
| `02079K107` | Class C. The common title is `CAP STK CL C` with issuer `ALPHABET INC` (2,424 rows). The same CUSIP is also titled `COM`, `Stock`, and `SC`. | about 2,800 |
| `02079K907` | `OPTIONS` on `ALPHABET INC` | 9 |
| `38259P508` | `CL A` on `GOOGLE INC`, the pre-rename name | 8 |

The issuer string is not stable either. The same Class A CUSIP appears as
`ALPHABET INC`, `Alphabet Inc`, `ALPHABET INC-CL A`, and `GOOGLE INC`.

## What this shows

Class A and Class C are two instruments. The CUSIP is what stays put.
`titleOfClass` does not: managers file the same CUSIP as `CAP STK CL A` and
as `COM`. Putting the class name on the Company would mix two instruments
into one legal entity, and grouping by title would split one instrument
across many spellings.

A third CUSIP, `02079K907`, is an option on Alphabet, not another share
class. Eight rows still carry the old Google Class A CUSIP `38259P508`.
