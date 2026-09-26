# 03: An ETF share is issued by the trust, not the adviser

**What to build:** An ETF CUSIP is a Security issued by the Fund Company the filing names, once that trust is an existing Company. `ISHARES TR` issues `464287200`. BlackRock does not. The same split holds for `VANGUARD INDEX FDS` and `SPDR S&P 500 ETF TR`. A name-only jump to the adviser is rejected.

**Blocked by:** 02: Point ISSUED_BY at a mastered Company.

**Status:** ready-for-agent

- [ ] `464287200` with issuer `ISHARES TR` is `ISSUED_BY` the iShares Trust Company, not BlackRock.
- [ ] `922908363` is issued by the Vanguard trust Company, not Vanguard the adviser.
- [ ] `78462F103` is issued by the SPDR trust Company, not SSGA.
- [ ] Passing only the adviser name, with no trust Company, writes no `ISSUED_BY`.
