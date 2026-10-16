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
