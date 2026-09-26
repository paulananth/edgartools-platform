# 02: Point ISSUED_BY at a mastered Company

**What to build:** When a 13F issuer name is an alias of a Company that already exists, the Security is issued by that Company. `GOOGLE INC` and `ALPHABET INC` are one issuer. A name that matches no Company leaves the Security in place and writes no `ISSUED_BY`. The filing does not mint a Company.

**Blocked by:** 01: Publish one Security per 13F CUSIP.

**Status:** ready-for-agent

- [ ] Class A and Class C are both `ISSUED_BY` the one Alphabet Company when either filed name is given.
- [ ] An unmatched issuer name produces the Security and no `ISSUED_BY`.
- [ ] No new Company is created from a 13F issuer string.
