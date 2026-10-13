# 02: Point ISSUED_BY at a mastered Company

Priority: 22, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/security-mastering/issues/02-issued-by-a-mastered-company.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

**What to build:** When a 13F issuer name is an alias of a Company that already exists, the Security is issued by that Company. `GOOGLE INC` and `ALPHABET INC` are one issuer. A name that matches no Company leaves the Security in place and writes no `ISSUED_BY`. The filing does not mint a Company.

**Blocked by:** security-mastering 01: Publish one Security per 13F CUSIP.

**Status:** ready-for-agent

- [ ] Class A and Class C are both `ISSUED_BY` the one Alphabet Company when either filed name is given.
- [ ] An unmatched issuer name produces the Security and no `ISSUED_BY`.
- [ ] No new Company is created from a 13F issuer string.
