# 03: An ETF share is issued by the trust, not the adviser

Priority: 23, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/security-mastering/issues/03-etf-share-issued-by-the-trust.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

**What to build:** An ETF CUSIP is a Security issued by the Fund Company the filing names, once that trust is an existing Company. `ISHARES TR` issues `464287200`. BlackRock does not. The same split holds for `VANGUARD INDEX FDS` and `SPDR S&P 500 ETF TR`. A name-only jump to the adviser is rejected.

**Blocked by:** 22: Point ISSUED_BY at a mastered Company.

**Status:** findings recorded; waits for the operator's ruling on the issuer (asked 2026-10-16 20:05 ET)

- [ ] `464287200` with issuer `ISHARES TR` is `ISSUED_BY` the iShares Trust Company, not BlackRock.
- [ ] `922908363` is issued by the Vanguard trust Company, not Vanguard the adviser.
- [ ] `78462F103` is issued by the SPDR trust Company, not SSGA.
- [ ] Passing only the adviser name, with no trust Company, writes no `ISSUED_BY`.

## Findings (2026q2 N-PORT and GLEIF's 2026-09-11 golden copy, local; counts only) (2026-10-16 19:56 ET)

- Ticket 22 links a Security to GLEIF's record of the one issuer LEI its holdings state. The SPDR CUSIP's holdings state one LEI, GLEIF's record of the trust: it links to the trust today.
- The iShares CUSIP's holdings state 3 LEIs (the trust and two fund series), the Vanguard CUSIP's 5 (fund series, the trust, and the adviser): neither gets a link. The adviser is never chosen; no link is made by name.
- The LEI on most holdings is the fund series, not the trust, for both; 500 of the 3,392 CUSIPs filed with several LEIs tie for their top LEI. A majority vote does not give the trust.
- Each filed LEI replaced by its GLEIF umbrella (active `IS_SUBFUND_OF`, 73,664 pairs) before the one-LEI rule: 540 of the 3,392 multi-LEI CUSIPs get one issuer, the iShares one its trust; 1,967 CUSIPs linked today move from the fund series to its trust; the Vanguard CUSIP keeps 4 LEIs (3 with a fund manager's LEI dropped) and stays unlinked.
- Configuration for that option: a new source extract of GLEIF's relationship file giving the sub-fund pairs, a pair set the N-PORT issuer reading looks up (`coalesce` of the umbrella and the filed LEI). No GLEIF relationship reading exists in `rules/sources/gleif/` yet.

## Checklist

- [x] Measure the filed issuer LEIs of the three ETF CUSIPs and of every CUSIP with several (above) (2026-10-16 19:56 ET)
- [ ] The operator's ruling: the issuer is the umbrella trust (map each filed LEI to its GLEIF umbrella) or the filed fund series (the trust read through the sub-fund link)
- [ ] Configuration to the ruling, tested on invented records through the chain and the Merge Stage; counted on the real quarter
- [ ] PR, CI green, merge on the operator's word
- [ ] Learning → skill
