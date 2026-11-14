# Onboarding log: sec.ncen (SEC Form N-CEN data sets)

## Why

Operator, 2026-11-14: "Mutual funds and etf must be part of fund entity that must be tied to a company";
asked whether that company is the fund's adviser (from N-CEN) and whether to capture N-CEN from SEC:
"we need to model reality as close as possible so yes and yes". Then: "must use skill for all only build
generic scripts".

Target chain: share class (security) → fund series (`fund_structure`) → registrant trust (company), and fund
series → its adviser (company).

## The source

- Provider: SEC, Division of Economic and Risk Analysis, "Form N-CEN data sets": one zip per quarter of
  tab-separated tables (45 tables, a readme and a metadata file). A registrant files N-CEN once a year, so a
  quarter holds the registrants whose fiscal year ended in it.
- Captured 2026-11-14 with the operator's permission for these requests: the data set page, then four
  quarters, 2025q4 to 2026q3 (38 MB), under `~/.local/share/edgartools/mdm/captures/sec.ncen-datasets/<quarter>/`,
  receipts by data-operations' `capture_receipts.py --glob "*.zip"`.
- Filings per quarter: 2025q4 505, 2026q1 1,927, 2026q2 501, 2026q3 438.
- The repo held no N-CEN source, reader or rules before this.

## Profiling

- First run, four quarters as four inputs: only 2025q4 was read; the other three quarters' tables were
  refused with `Catalog Error: Table with name "SUBMISSION" already exists!` (each input names its tables by
  member name, so two inputs with the same members collide). Profiler gap, for its own ticket. Findings
  deleted, never approved.
- Second run, 2026q1 alone (the largest quarter; every quarter has the same tables), into
  `~/.local/share/edgartools/mdm/profiling/sec.ncen-2026q1/`: 51 parts, 98 s. The other quarters go to
  `compare` before they load.
- 2026q1: 1,927 filings, 1,796 registrants (file number), 6,471 fund series, 15,148 share classes,
  12,268 adviser rows (7,145 adviser, 4,852 sub-adviser, 271 terminated).

## What MDM already holds (hosted, read-only, 2026-11-14)

| N-CEN value | In N-CEN 2026q1 | Already an MDM identifier |
|---|---|---|
| Fund series id | 6,471 | 6,247 (`sec_series_id`, from N-PORT) |
| Fund series LEI | 6,756 | 6,498 (`lei`) |
| Registrant CIK | 1,796 | 1,041 (`cik`) |
| Share class ticker | 12,282 | 1,558 (`ticker`) |
| Adviser CRD as filed | 841 | 0 (`crd`) |
| Adviser CRD, leading zeros set aside | 840 | 706 (`crd`, from Form ADV) |
| Adviser LEI | 641 | 20 (`lei`) |

N-CEN writes a CRD number as 9 digits with leading zeros; Form ADV writes it without them. 7,057 fund series
name a current adviser.

## The other quarters (compare)

`profile_data.py compare` of 2025q4, 2026q2 and 2026q3 against the approved 2026q1 findings: about 500 drift
items each, none on a column the parts read. The header lines of SUBMISSION, REGISTRANT, FUND_REPORTED_INFO,
ADVISER and SHARES_OUTSTANDING are the same in all four zips, so the `column_new` and `column_missing` items
on derived parts (`FUND_REPORTED_INFO.LEI`, `REGISTRANT.FILE_NUM`) are the profiler's split of a part, not the
files. Volume and distribution items follow the quarter: a registrant files once a year, so each quarter holds
the fiscal years that ended in it (2026q1 is the peak). Kept for the parts:
- SHARES_OUTSTANDING's key gains TICKER in the other quarters: over four quarters 31,265 rows, 31,253 fund
  and class pairs; 5 classes give two tickers in one filing.
- Over four quarters: 14,191 fund rows, 12,422 series; 873 series are in more than one filing; 132 of the
  3,371 filings are N-CEN/A.

## Parts, in order (plan-parts)

1. **Fund series** (`sec.ncen.fund`, `sec.ncen.fund.v1`, kind `fund_structure`): FUND_REPORTED_INFO, joined
   by series id and LEI. `profile.yaml` (the public summary, names and counts only) is in this folder.
2. **Advisers** (kind `company`, by CRD and LEI) and the series → adviser link `INVESTMENT_ADVISER_TO`
   (already in RDM's `mdm-relationship-types`; its definition names N-CEN). Blocked on a question: N-CEN
   writes a CRD with leading zeros and `normalize_identifier@crd-v1` keeps every digit, so no N-CEN CRD
   matches a Form ADV one; the declared identifier grammar (`rules/identifiers/`) has no way to drop leading
   zeros, so the fix is a new normalizer version: code, a ticket, the operator's word.
3. **Share classes** (kind `security`, by SEC class id) linked to their series. Blocked on a question:
   `ISSUED_BY` holds one issuer at a time (`one_target`); N-PORT's issuer claim points a series' securities
   at the umbrella trust (ruling 2026-10-17), so a class → series issuer would set both links aside.
4. **Registrant trusts** (kind `company`, by CIK). N-CEN's REGISTRANT carries N-PORT's registrant columns.

## identify (part 1)

`sec.ncen.fund`, source code `sec.ncen.fund.v1`, capture family `sec.ncen-datasets`; not a new domain
(`fund_structure` holds N-PORT's series). N-CEN's SUBMISSION.tsv and REGISTRANT.tsv have the columns
N-PORT's readings use, so the fund series reads its dates and registrant CIKs through
`sec.nport.registrant/submissions.yaml` and `sec.nport.registrant/source.yaml`, unchanged: one path for
both data sets. Its reduce, LEI pair and combine steps are N-PORT's (a step names files of its own folder).

## map (part 1)

- Record key: SERIES_ID, upper-cased; 773 rows over four quarters name none and are not read; 1 series id
  is not "S and nine digits" and is refused by the `sec_series_id` format.
- LEI: 9 all-zero LEIs and 26 blank are no value; 11 LEIs filed for two series and 1 series filing two LEIs
  do not join (N-PORT's one-to-one guard).
- Filing date: `DD-MON-YYYY`, the format N-PORT's reading already turns into a date.
- Effective time: the latest filing date, an observation (operator, 2026-11-06).
- Field: `name` (FUND_NAME). N-PORT wins a field over N-CEN (`defaults.sources`).
- Merge rules: `ncen-fund-series` and `ncen-fund-lei` in `fund_structure.yaml`, listed in the policy.
- `IS_SUBFUND_OF` is left to part 4, which decides the registrant record N-CEN points at.

## check and load (part 1)

- `rules check --source sec.ncen.fund`: ok. Mapping Documents regenerated: `sec.ncen.fund`, `fund_structure`, and
  `sec.nport.fund` (its "Who wins" row now names N-CEN second).
- Disposable store `ncen-test`: N-PORT's 2026q2 series first (its merge done; its silver links step refused an
  empty delivery, since no registrant was loaded), then N-CEN 2025q4 to 2026q3.
- Each later quarter is a new publication of the same series: loaded at revision 0 it was refused ("Source
  native revision has contradictory publications"), as data-operations says; quarters load with `--revision`
  0, 1, 2, 3 in quarter order.
- Result: 12,953 N-CEN records of 12,412 series; 11,895 Funds hold both sources, 512 are new from N-CEN, 1,042
  are N-PORT's only; set aside 1 (`invalid_sec_series_id`) and 9 (`invalid_lei_checksum`); 6 to review
  (`conflicting_identifiers`); no identifier held by two Funds. A second load of 2025q4: "0 documents loaded,
  1 already loaded before".

## Questions and answers

(one at a time, below)

1. **Approve the 2026q1 findings, with the parts mapped onto existing kinds and onboarded in this order:
   fund series → `fund_structure` (series id, LEI); advisers → `company` (CRD, LEI) with a series → adviser
   link in N-CEN's own terms; share classes → `security` (class id, ticker) linked to their series;
   registrant trusts → `company` (CIK).** Service providers and yearly figures stay out for now.
   Operator, 2026-11-14 09:31 ET: "yes, use skills, rules, and generic scripts, follow existing architecture,
   mdm, bookkeeping, rdm, change journal, db for storage". Recorded with `profile_data.py approve`.
