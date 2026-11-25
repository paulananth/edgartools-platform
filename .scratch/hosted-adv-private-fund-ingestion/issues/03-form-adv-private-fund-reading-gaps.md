# 03: Form ADV private-fund reading gaps the spec reviews found

Type: task
Status: resolved
Blocked by: none
Blocks: none
Labels: wayfinder:task

Found by the two spec reviews of ticket 01 (2026-11-24); the hosted reload ran with them open, each measured as small.
Moved here from ticket 01 so that ticket closes with the hosted load.

Operator, 2026-11-25: "All six, one at a time" (scope), then a ruling on each below. Measured on a fresh disposable store
loaded from the March and June captures (118,554 Fund Structures, 126,295 adviser links, 3,141 feeder links) and in the
tests of `tests/integration/test_adv_private_funds.py` (PG16).

## Checklist

- [x] Two advisers naming different masters for one feeder. Operator: "Latest filing wins, pinned by a test (Recommended)". No rules change; `test_a_feeder_two_advisers_report_with_different_masters_goes_to_the_latest_filings_master` pins it, and documents behaviour that exists, so it passes before and after; with the combine changed so the earliest filing wins (`mode: first`) it fails, because the feeder's target becomes the other master (2026-11-25 14:10 ET)
- [x] Contradictory roles. The ticket's reading (one filing stating a fund in both roles) is not in the data: 0 of 170,157 filing-and-fund records state both, so the first change ("Keep both, as two capacities", an aggregation of a filing's rows in the combine) changed no link (126,295 before and after) and was removed. The real case is two filings of one adviser, in one month, naming one fund in different roles: 2 pairs of 6,325 pairs with two or more filings in a month, 4 links of 126,295. Each record restates its capacities and a month's records carry one date, so the tie drops both links. Operator: "Record it as a known limit (Recommended)"; `test_two_filings_of_one_adviser_naming_a_fund_in_different_roles_in_one_month_make_no_link` pins it (it documents behaviour that exists, so it passes before and after: no failing-before assertion). Ordering by the filing's own date needs a Base join (or the engine's same-date tie), not built (2026-11-25 14:10 ET)
- [x] The "latest" 7.B(1) row ordered FilingID as text: it orders by `filing_number`, the filing's number as an integer (`integer: {path: FilingID, from: record, on_invalid: error}` in the two 7.B(1) readings, `order_by: [filing_number]`). `test_the_latest_filing_is_the_larger_filing_number_whatever_its_width` fails with the text order (a ten-million filing sorted before a nine-million one) and passes with the number. Real FilingIDs are all seven digits with no leading zero (23,167 of 23,167), so no real row changes order (2026-11-25 14:10 ET)
- [x] Conflicting duplicate rows (one filing's rows of one fund in two tables with different roles): `distinct_on` keeps the first table's row; pinned by `test_a_filing_stating_a_fund_in_two_tables_with_different_roles_keeps_the_first_tables_row`; it documents behaviour that exists, so it passes before and after; none exist in the real files (0 of 170,157) (2026-11-25 14:10 ET)
- [x] An ERA filing with an 801- number left out with no set-aside reason (20 in March, 90 in June). Operator: "Close both as measured no-loss (Recommended)": every such filing is also in the registered advisers' file and is read from there (the first test covers the filing, its funds and its link), so nothing is lost; no reason is built, since nothing would read it (2026-11-25 14:10 ET)
- [x] The 7.B readings carry no section or filing-action field. Same ruling: nothing reads either (links, Fund Structures and evidence do not), so none is built (2026-11-25 14:10 ET)
- [x] The real-data proof of the numeric order on a fresh store, March and June loaded through `edgar-warehouse load` with the current engine (the integer column raised no error on any real FilingID): 118,554 Fund Structures, 126,295 adviser links, 3,141 feeder links, all equal to the earlier proof (2026-11-25 14:10 ET)
- [x] Learning → skill: none; the same-date tie and the "each record restates its capacities" rule are in the reference already (2026-11-25 14:10 ET)
