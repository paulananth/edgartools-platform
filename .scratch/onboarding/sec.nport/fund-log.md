# Onboarding log: N-PORT part 3, the Fund (ticket 79)

## identify (2026-10-15 23:12 ET)

- Source folder `rules/sources/sec.nport.fund/`, code `sec.nport.fund.v1`, family `sec.nport-datasets`. Kind `fund_structure` (in `KINDS`; profile `fund`): a **new domain**, no merge rules until this part. Ruling (operator, 2026-10-14, findings q17): "Series id and LEI join (Recommended)"; IS_SUBFUND_OF its registrant, onboarded together (q16).

## What the files hold (2026q2, counts only, no request)

- `FUND_REPORTED_INFO.tsv`: 14,416 filings; **12,944 series ids**, every one "S" and nine digits; 729 filings name no series (single-fund registrants: the registrant Company is the fund). 676 series file more than once in the quarter; 1 series appears under two registrant CIKs.
- Series LEIs: 12,891 distinct; 13 series file none; 15 LEIs are filed for two series; 1 series files two LEIs.
- The local GLEIF Golden Copy (2026-09-11): **12,884 of 12,891 series LEIs are in it**: 12,854 in category FUND (GLEIF's contract sorts them as probably `fund_structure` and creates none), **30 in GENERAL** (GLEIF's contract makes them Companies).

## A gap the link meets: the `fund` profile's start date

IS_SUBFUND_OF (`rules/merge/relationships.yaml`) needs the `fund` profile at both ends over the link's whole period (`relationships.py:272`). A profile needs a start date (survivorship refuses an undated one, `undated_profile`), and that date is part of the profile's identity (`PROFILE_IDENTITY`), so a date that moves with each quarter makes a new profile each quarter. **No source maps a profile today** (`grep profiles: rules/` finds none; platform validation research 06 said every profile-gated link would wait as `missing_endpoint_profile`): this is a platform gap, not only N-PORT's.
- Registrant end: the SEC filer capture (all-76230) holds the registration filing (N-8A) for **1,119 of 1,947** registrants (1,105 of the 1,471 whose whole history is captured; 366 of those have none, 462 have older pages not captured). A fixed date where it exists.
- Series end: **no local capture states when a series began.** N-PORT gives the filing and report dates only, which move each quarter.

Built so far, independent of the date: `rules/identifiers/sec_series_id.yaml`; `rules/merge/kinds/fund_structure.yaml` (`nport-fund-series`, `nport-fund-lei`, declared, not switched on; Identifier Contracts for `sec_series_id` and `lei`). The policy loads and passes `check_policy`. The source extract waits for the ruling and for #1001 (its filing-date reading).

## Ruling: the link (2026-10-16 06:33 ET)

- Operator, asked how part 3 handles IS_SUBFUND_OF with no stated series start: **"Funds now, link later (Recommended)"**. The Funds are mastered by series id and LEI now; each keeps its registrant's CIK as a lookup-only cross-reference (`nport_registrant_cik`); IS_SUBFUND_OF is added once a source states when a series began.

## The test run (2026-10-16 06:33 ET, tested locally)

`fund_test_run.py`, report `fund-test-run.json` (counts only), 17 s, reusing part 2's verified readings of filing dates and registrants (nothing read twice). The first attempt stopped at the reduction: a filing naming no series has a null key, which a reduction refuses; fixed with the table's `select` (a blank series id is not read).
- 13,687 filings with a series; every one dated and tied to its registrant. **12,944 Funds**; 676 with several filings; the latest filing matches a direct calculation for 12,944 of 12,944; 9 series changed name in the quarter.
- `sec.nport.fund.v1`: **12,937 accepted**; 7 set aside `invalid_lei_checksum` (as many as the series LEIs GLEIF does not hold). Series id 12,937, LEI 12,924, registrant CIK 12,937. **15 LEIs on two Funds.**

## The Proving Run: stopped (2026-10-16 06:33 ET)

`fund_proving_run.py` (the two Fund rules switched on in the run's copy of the policy only; container removed). The first pass stopped at a batch: **"Identity decision has unresolved authoritative identifier or kind conflict"**. Cause: the 15 LEIs filed for two series. The second series finds no Fund by its series id, the LEI rule joins it to the first series' Fund, and that Fund then holds two series ids, which the Merge Stage refuses for the whole batch. Not yet decided how to treat a shared LEI (as part 1 did for an ISIN shared by two CUSIPs: join by LEI only when one series in the quarter states it). Stopped here on the operator's word ("after this stop and wait").

## A shared LEI joins nothing (2026-10-16 08:06 ET)

Decided from part 1's precedent (an ISIN filed with several CUSIPs is attached to none), after the operator's "continue with goal": an LEI joins a Fund only when its series files one LEI and no other series files it in the quarter. Configuration only: `reduce.yaml` counts series per LEI and LEIs per series (a missing LEI counts under empty text, since a reduction refuses a null key); `lei-pairs.yaml` joins both counts to each series-and-LEI pair; `combine.yaml` keeps the LEI where both are 1. Every filed LEI stays on the Fund as a lookup-only cross-reference (`nport_series_lei`).
- Test run again (10 s): **12,874 series carry their LEI**, the same series and LEI as a direct count for 12,944 of 12,944; 15 LEIs filed for two series and the 1 series filing two LEIs join by series id only. **0 LEIs on two Funds.** 12,937 accepted, 7 set aside `invalid_lei_checksum` (a joining LEI with a bad check digit), as before.
- Not handled: if exactly one series in a quarter filed no LEI, the empty text would pass as "one to one"; in 2026q2, 13 series file none. A later quarter's test run shows it.

## The one Proving Run (2026-10-16 08:06 ET, tested locally, passed)

`fund_proving_run.py`, report `fund-proving-run.json` (sha256 792af1f5...e0d56e58, counts only). Docker no longer starts on this Mac (macOS 27 refuses Lima built for Intel under Rosetta; MacPorts' colima and limactl are x86_64), so the run used the fixtures' local PostgreSQL 16 (`PG16_SERVER=pgserver`, deleted afterwards). Both Fund rules switched on only in the run's copy of the policy, stamped "proving-run", with stand-in verifications.
- First pass 48 s, 28 batches: **12,937 Funds**, 12,937 bind decisions; **0 series ids and 0 LEIs on two Funds**; 12,867 hold a joining LEI. 7 records wait as open reviews (`invalid_lei_checksum`).
- **Second pass (9 s) changed nothing.**
- The 30 series LEIs GLEIF holds as GENERAL (a Company in GLEIF's contract) cannot join these Funds: the LEI contract joins only records of one kind (`kind_equal@1`). Logged for when GLEIF's FUND records are mastered.

## Metadata and tests (2026-10-16 08:06 ET)

- Mapping Documents: `rules/sources/sec.nport.fund/MAPPING.xlsx` and `rules/merge/kinds/fund_structure.xlsx` (new); `rules mapdoc check` passes.
- Tests: the expected Mapping Document list gains the source and the kind; the identifier type's pinned digest is added; a new test of the series id's shape (invented values). Rules tests and the whole MDM test folder: 954 pass.

## Approval (2026-10-16 08:06 ET)

- Operator's standing words, **"Approved the rules always"** (2026-10-15 18:56 ET), on the test run and this Proving Run: approved the new domain's merge rules `rules/merge/kinds/fund_structure.yaml` (`nport-fund-series`, `nport-fund-lei`, version 2026-10-15.1, declared; Identifier Contracts for `sec_series_id` and `lei`), the identifier type `sec_series_id` v1, and the Dataset Contract `sec.nport.fund.v1` with its source extracts. No quality file: profiling found no defect for a check.
- Not covered: **switching on** the two Fund rules with their Identifier Contracts' verification (this report's sha256), and the merge of this PR. Each waits for the operator.
