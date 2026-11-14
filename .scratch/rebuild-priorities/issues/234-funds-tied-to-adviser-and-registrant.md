# 234: Funds tied to their adviser and their registrant (SEC Form N-CEN)

Type: task. Status: open. Blocked by: none.

## Why

Operator, 2026-11-14: "Mutual funds and etf must be part of fund entity that must be tied to a company". Asked
whether that company is the fund's adviser, from N-CEN, and whether to capture N-CEN from SEC: "we need to model
reality as close as possible so yes and yes". Then: "must use skill for all only build generic scripts", and, on
the findings: "yes, use skills, rules, and generic scripts, follow existing architecture, mdm, bookkeeping, rdm,
change journal, db for storage".

Target chain: share class (security) → fund series (`fund_structure`) → registrant trust (company), and fund
series → its adviser (company). The onboarding log is `.scratch/onboarding/sec.ncen/onboarding-log.md`.

## Parts

- [x] Capture four quarters of the N-CEN data sets with the operator's permission; receipts by `capture_receipts.py` (2026-11-14 09:50 ET)
- [x] Profile 2026q1 and record the operator's approval of the findings (`profile_data.py approve`) (2026-11-14 09:50 ET)
- [x] Compare the other three quarters with the approved findings: no drift on a column the parts read (2026-11-14 09:50 ET)
- [x] Plan the parts (2026-11-14 09:50 ET)
- [ ] ~~Write `profile.yaml`~~ deferred to the first N-CEN silver part: its 79 tables are not landed, and two parts name one table (catalog test, CI on PR 1764)
- [x] Part 1, fund series: `sec.ncen.fund` into `fund_structure` by series id and LEI, loaded in a disposable store after N-PORT's 2026q2 series: 12,953 records of 12,412 series; 11,895 Funds hold both sources, 512 are new, 1,042 are N-PORT's only; 10 set aside (1 series id shape, 9 LEI check digits), 6 to review (conflicting identifiers), no identifier on two Funds; a second load found nothing to do (2026-11-14 09:50 ET)
- [ ] Part 1 loaded on the hosted store (the operator's word)
- [ ] Part 2, advisers: decide how an N-CEN CRD (written with leading zeros) matches a Form ADV CRD
- [ ] Part 2, advisers: `company` by CRD and LEI, and the series → adviser link `INVESTMENT_ADVISER_TO`
- [ ] Part 3, share classes: decide the issuer of a share class while N-PORT's issuer claim names the umbrella trust (ruling 2026-10-17)
- [ ] Part 3, share classes: `security` by SEC class id, linked to their series
- [ ] Part 4, registrant trusts: `company` by CIK, and the series → trust link for series N-PORT does not file
- [x] Profiler: several inputs whose zips hold the same member names collided (`Table with name ... already exists`); a table whose name an earlier input took now gets its input's name in front (`test_two_inputs_holding_tables_of_one_name_are_both_profiled` failed before with that error) (2026-11-14 10:28 ET)
- [x] Learning → skill, so far (2026-11-14 10:28 ET):
  - data-profiling: a data set published per period is profiled once and the other periods compared;
    read drift against the header lines first; `catalog` waits for a silver part.
  - data-onboarding: a sibling data set reads through the other source's readings (`from:`); periods load
    with rising `--revision`; what a new source moves in the tests; one identifier with two paddings
    needs a normalizer version.
- [ ] Learning → skill for parts 2 to 4
