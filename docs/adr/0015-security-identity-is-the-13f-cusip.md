---
status: accepted
---

# A Security is one 13F CUSIP, issued by the filer, not by the adviser

Accepted 2026-09-25. A Security is one financial instrument. Its identity is the 13F CUSIP, so an invented company's Class A (`000000AA1`) and Class C (`000000AC9`) are two Securities of one Company. The display title is the normalized class, or the instrument kind when there is no class (`Option`). Filed spellings stay on the holding. `ISSUED_BY` points at the mastered issuer and can wait until that issuer is known. For an operating company the issuer is that Company, including a rename of the company. For an ETF share the issuer is the Fund Company that files, the trust named on the 13F. The sponsors manage the series, and N-CEN names them as investment advisers. Company mastering joins a CIK to a LEI and does not merge a trust into its sponsor by name. The old MDM path that minted one Security from a CUSIP and another from a Form 4 title is not the identity.
