# 234: Funds tied to their adviser and their registrant (SEC Form N-CEN)

Type: task. Status: resolved (the hosted load and correction are ticket 238's). Blocked by: none.

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
- [ ] ~~Parts 1 and 2 loaded on the hosted store (the operator's word)~~ deferred to 238: the hosted run is done separately (operator, 2026-11-17: "hosted run will be done seperately"); its chain holds the N-CEN steps
- [x] Part 2: why no "Terminated" row ended a link: none of the 493 pairs it names is held in an earlier quarter; the sighting that held each is in the year before the four captured quarters (measured on the captures) (2026-11-14 13:07 ET)
- [x] Part 2, advisers: decide how an N-CEN CRD (written with leading zeros) matches a Form ADV CRD: `normalize_identifier@crd-v2` (operator: "yes"; PR 1766)
- [x] Part 2: name the link's capacities with N-CEN's own adviser types, `advisor` and `subadvisor`, in RDM `mdm-relationship-types` 5 (operator: "yes but any type must also be added to rdm"; PR 1768) (2026-11-14 13:07 ET)
- [x] Part 2: a reverse limit counts values as compared, and a restated role keeps its earliest start (operator: "Yes"; PR 1772: tests that failed before) (2026-11-14 13:07 ET)
- [x] Part 2, advisers: `sec.ncen.adviser` into `company` by CRD (LEI lookup only), and the series → adviser link `INVESTMENT_ADVISER_TO` from `sec.ncen.fund`, loaded in a disposable store with one Form ADV month and four N-CEN quarters: 1,491 advisers, 185 joined Form ADV (all the CRDs that month holds), 20,344 links (12,340 advisor onto 12,214 series, 8,004 subadvisor onto 4,846), 0 held back for a role start; 5 joined advisers in review over Form ADV's own several-CIK rule (2026-11-14 13:07 ET)
- [x] Part 3: decide the issuer of a share class: its fund series, the trust reached through `IS_SUBFUND_OF` (operator, 2026-11-14, after the research: "Yes", replacing "Umbrella trust (Recommended)", 2026-10-17). Evidence, four example funds: under the Investment Company Act each series is a separate investment company with its own shareholders and votes (SEC IM guidance 2014-06, Rule 18f-2); under the Delaware Statutory Trust Act a series is ring-fenced but not a legal entity apart from its trust; GLEIF registers each series as a FUND entity `IS_SUBFUND_OF` its trust and `IS_FUND-MANAGED_BY` its adviser; the CUSIP issuer number is the trust's; N-PORT holders of one example ETF name the series' LEI 180 times and the trust's 70 (2026-11-14 16:41 ET)
- [x] Part 3: N-PORT's share issuer is its fund series (`sec-nport-security-v8`), proved on a disposable store with N-PORT 2026q2: 420,690 Securities; 2,465 fund shares issued by 2,311 fund series, 240,635 Securities issued by 22,991 LEI issuers (companies, and trusts that holders name in place of a series), 177,590 with no issuer named (2026-11-14 16:41 ET)
- [ ] ~~Remove GLEIF's `subfund-pairs` target~~ deferred: no reader is left, but removing it changes GLEIF's rules, which may reprocess GLEIF on the hosted store; its own ticket
- [x] Part 3, share classes: decide how a class finds its Security: its class id, else a ticker one Security holds (several go to review), else a new Security by class id (operator, 2026-11-14: "Class id, then ticker (Recommended)"; 3,326 of 25,858 N-CEN tickers are held by one hosted Security, 19 by several) (2026-11-14 16:41 ET)
- [x] Part 3, share classes: `sec.ncen.class` into `security` by SEC class id (rules `ncen-class-id`, `ncen-class-ticker`), issued by its N-CEN series, in two steps (read, combine; ticket 235). Loaded N-CEN 2026q1 into a disposable store: 15,148 classes, 15,148 Securities, 15,141 issued by 6,458 series (7 of a fund that names no series), no review; a filed "ticker" longer than nine characters (1) is dropped and its class kept. The ticker join, a reused ticker's review and a creation by class id: `tests/integration/test_ncen_share_class.py` (2026-11-14 17:17 ET)
- [x] Part 4, registrant trusts: `sec.ncen.registrant` into `company` by CIK (rule `ncen-registrant-cik`; LEI lookup only), and the series → trust link `IS_SUBFUND_OF` from `sec.ncen.fund`, in two steps (read, combine). Loaded N-CEN 2026q1 into a disposable store: 1,796 registrants, 1,796 Companies, 6,465 series linked to 747 trusts, 0 review. The LEI is lookup only: joining by it put several trusts on one Company (1,712 Companies from 1,796 registrants), since 25 LEIs are filed by 120 CIKs, and 19 filed LEIs fail their check digits (2026-11-14 17:52 ET)
- [x] 2026-11-17 06:32 ET Finding: N-PORT's registrant rule joins by LEI too (`nport-registrant-lei`); on the hosted store 3 Companies hold 2 registrant CIKs and 1 holds 3. Same cause as part 4's. Decided (operator, 2026-11-17, asked to choose between join only if no other CIK, lookup only, or leave it: "Join only if no other CIK (Recommended)"): the Company `lei` contract `yields_to: [cik]`, so the LEI still finds a GLEIF or custodian Company, but a Company that holds another CIK, or a file-mate with another CIK, makes the registrant join by its CIK alone and be created by it (`merge._hold_conflicts`, beside `conflicts_with`, which sends to review). Tests `test_a_registrant_whose_lei_finds_a_company_holding_another_cik_creates_its_own` (`assert 1 == 2`: one Company) and `test_two_registrants_of_one_file_sharing_a_lei_stay_two_companies` (one Company held both CIKs) failed before; the LEI it gave way on is withheld, so one Company holds it and a later GLEIF record with it still finds one (`assert not ['<lei>']` and `assert 2 == 1` without the withhold; found by the review); a record stating no CIK still joins whatever CIK the Company holds (`test_a_record_stating_no_cik_joins_the_company_its_lei_finds_whatever_cik_it_holds`). 88 mastering adapter tests pass on PostgreSQL, 84 on MySQL; policy digest updated in `company-mastering-records.json`. Known limits, from the review: within one file, a record sent to review for another reason still counts as the LEI's first stater, so a later file-mate gives way (subject order, rare: its CIK must reach two Companies); a contract naming both `conflicts_with` and `yields_to` on one identifier is not refused.
- [ ] ~~Correct the hosted Companies the LEI joined (4 Companies, 9 registrant CIKs)~~ deferred to 238: the hosted run, done separately. A bind already made stays standing under a changed rule (no correction command yet), so only a load into a fresh store separates them
- [x] Profiler: several inputs whose zips hold the same member names collided (`Table with name ... already exists`); a table whose name an earlier input took now gets its input's name in front (`test_two_inputs_holding_tables_of_one_name_are_both_profiled` failed before with that error) (2026-11-14 10:28 ET)
- [x] Learning → skill, so far (2026-11-14 10:28 ET):
  - data-profiling: a data set published per period is profiled once and the other periods compared;
    read drift against the header lines first; `catalog` waits for a silver part.
  - data-onboarding: a sibling data set reads through the other source's readings (`from:`); periods load
    with rising `--revision`; what a new source moves in the tests; one identifier with two paddings
    needs a normalizer version.
- [x] 2026-11-17 06:32 ET Learning → skill: data-onboarding, "An identifier a filer states about itself": where the join is wanted anyway, the contract names the key it gives way to (`yields_to`).
- [x] Learning → skill for parts 2 to 4: data-onboarding, Examples: a self-stated identifier joins only where it
  is one to one (else lookup only); a secondary key finds a master only where one holds it; a link's capacity
  is the source's term, added to RDM (2026-11-14 20:23 ET)
