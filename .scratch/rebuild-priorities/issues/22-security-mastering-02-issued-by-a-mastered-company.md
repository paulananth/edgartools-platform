# 02: Point ISSUED_BY at a mastered Company

Priority: 22, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/security-mastering/issues/02-issued-by-a-mastered-company.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

**What to build (rewritten for the rebuild, 2026-10-16 08:51 ET):** a Security is issued by the entity that holds its issuer's LEI. Operator, 2026-10-16, asked how a Security finds its issuer: **"By issuer LEI (Recommended)"**: no name matching; a Security whose issuer states no LEI gets no ISSUED_BY yet. The old plan (match a 13F issuer name to a Company's aliases) is replaced.

Measured (N-PORT 2026q2, counts only): 3,394,415 of 5,347,869 holding rows state an LEI-shaped issuer LEI; 28,424 distinct issuers; the local GLEIF Golden Copy (2026-09-11) holds 28,397 of them: 24,124 GENERAL (a Company in GLEIF's contract), 3,639 FUND, 580 RESIDENT_GOVERNMENT_ENTITY, 38 BRANCH, 10 INTERNATIONAL_ORGANIZATION, 6 SOLE_PROPRIETOR.

**Status:** in progress (Claude, branch `claude/issued-by-lei`).

- [x] The ruling: by issuer LEI 2026-10-16 08:51 ET
- [x] Configuration only: `issuers.yaml` (holdings' CUSIP and issuer LEI, read once, an LEI-shaped value only), `issuer-reduce.yaml` (LEIs per CUSIP), `combine.yaml` (the LEI of a CUSIP filed with exactly one, part 1's one-to-one rule), and an `ISSUED_BY` link in `sec.nport.security.v1` to GLEIF's record of that LEI (`target_source: gleif.level1.v1`); the link waits until that record is mastered; the link has no start of its own (the holdings state none), so MDM starts it when first seen (test run below) 2026-10-16 09:17 ET
- [x] Test run: Securities with a link, against a direct count from the same file (`.scratch/onboarding/sec.nport/issuer-test-run.json`, `issuer_gap.py`): 216,560 Securities with exactly one ISSUED_BY, every one a CUSIP whose holdings name exactly one issuer LEI, none linked otherwise; 3,392 CUSIPs naming several LEIs get none; the other 845 with one LEI are all set aside for a failing CUSIP check digit; contract outcome as part 1 (383,612 accepted, 1,769 invalid_cusip_checksum, 1 invalid_cusip); 7.8 min 2026-10-16 09:17 ET
- [ ] Proving Run: the issuers' GLEIF records (Companies) and the N-PORT Securities; ISSUED_BY resolved to a Company for the GENERAL issuers; the rest wait; second pass changes nothing
  - [x] Proving Run 1 (`.scratch/onboarding/sec.nport/issuer-proving-run.json`, `issuer_proving_run.py`, pgserver): 383,612 Securities, 0 LEIs on two entities, second pass changed nothing; 28 min first pass, 11.5 min second (ticket 96's index). **No issuer became a Company**: the 24,124 GENERAL issuer records end as open reviews `binding_required`, since a GLEIF record only joins a Company an SEC record created; the other 4,273 are set aside (`unsupported_identity_kind`); so 0 of the 216,560 links resolve 2026-10-16 09:59 ET
  - [ ] Decision (operator): whether a GLEIF entity creates its Company by its LEI, as an N-PORT registrant does by its CIK; then Proving Run 2
- [ ] ~~Class A and Class C both `ISSUED_BY` the one Alphabet Company when either filed name is given~~ replaced by the ruling: both classes carry the issuer's one LEI, so both link to its Company (checked in the Proving Run: Securities per issuer)
- [x] An issuer with no LEI: the Security and no `ISSUED_BY` (test run: 383,612 accepted, 216,560 linked; the rest carry no link) 2026-10-16 09:17 ET
- [ ] No new Company is created from an issuer string or LEI (the link only names GLEIF's record; Proving Run: Companies equal GLEIF's GENERAL issuers)
- [ ] ISIN-only Securities (35,309): the same link, after the CUSIP Securities
- [ ] Issuers GLEIF holds as FUND (3,639) or government (580): their kinds are not mastered from GLEIF yet, so those links wait; logged
- [ ] Metadata, approval under the standing words, PR, CI green, merge on the operator's word
- [ ] Learning → skill
