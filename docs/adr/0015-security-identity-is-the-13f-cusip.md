---
status: accepted
---

# A Security is one 13F CUSIP, issued by the filer, not by the adviser

Accepted 2026-09-25. A Security is one financial instrument. Its identity is the 13F CUSIP, so Alphabet Class A (`02079K305`) and Class C (`02079K107`) are two Securities of one Company. The display title is the normalized class, or the instrument kind when there is no class (`Option`). Filed spellings stay on the holding. `ISSUED_BY` points at the mastered issuer and can wait until that issuer is known. For an operating company the issuer is that Company, including a rename such as Google to Alphabet. For an ETF share the issuer is the Fund Company that files, the trust named on the 13F. BlackRock, Vanguard, and SSGA manage the series. N-CEN names them as investment advisers. Company mastering joins a CIK to a LEI and does not merge a trust into its sponsor by name. The old MDM path that minted one Security from a CUSIP and another from a Form 4 title is not the identity.
