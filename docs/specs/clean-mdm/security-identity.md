# Security identity

Accepted 2026-09-25. Use these words. The decision record is
[ADR 0015](../../adr/0015-security-identity-is-the-13f-cusip.md).
The 13F reader in `crates/source-contract` emits the CUSIP, the filed title,
and the filed issuer name. It does not create the Security or `ISSUED_BY`.

| Decision | Rule |
| --- | --- |
| Identity | One 13F CUSIP is one Security. Class A and Class C are two Securities. |
| Title | The display title is the normalized class, such as Class A. `CAP STK CL A`, `CL A`, and `CLASS A` are that title. A CUSIP filed as `OPTIONS` is titled Option. A title that names neither a class nor a kind waits. |
| Filed words | Each holding keeps the title and issuer name that manager wrote. |
| Issuer | `ISSUED_BY` points at one mastered issuer. `GOOGLE INC` and `ALPHABET INC` are one Company. The Security can exist before that link is known. A 13F issuer string does not mint a Company. |
| ETF share | The CUSIP is a Security issued by the Fund Company, the trust that files. `ISHARES TR`, `VANGUARD INDEX FDS`, and `SPDR S&P 500 ETF TR` are those Fund Companies. |
| Adviser | BlackRock, Vanguard, and SSGA `MANAGES_FUND` the series. They are not the issuer. N-CEN is the filing that names the adviser. N-PORT is the series holding other Securities. |
| Form 4 | A Form 4 that names the class for that issuer attaches to the existing CUSIP Security. It does not create another Security for the same CUSIP. |
| Not a Company field | A CUSIP, a class, and an ETF share are not fields of the Company. |

Company mastering does not do the trust-to-sponsor jump. It keys a Company by CIK and joins a GLEIF LEI. A fuzzy name is not enough to merge two Companies. See `docs/research/company-mastering-fund-issuer-2026-09-25.md`.
