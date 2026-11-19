# The finish phase takes over five minutes

Status: open
Type: bug

Operator, 2026-11-19 15:29 ET: "Finish can not take more than 5 min". After the first hosted load, `load_chain.py --finish` (the links
table, then each silver table's master ids) had run 31 minutes and was still on its fifth table of ten.

## What was measured (read-only, hosted store, 15:30 ET)

- `silver links` took about 21 minutes (14:58 to 15:19). Its one statement is a `body like` scan of `mastering_record`: 381 s, 1.2 M blocks read.
- `silver refresh-ids` runs one lookup per link: `select subject,entity_id from mastering_record where entity_id is not null and subject in (...)`
  for 2,000 keys at a time. 3,219 calls, 6.4 M rows returned (the table holds 3.9 M: a key is read again for each link and table), 3.8 M blocks
  read, 0.95 s a call. `subject` is a digest, so keys in one batch sit on different heap pages: about one disk read a row.
- `mastering_record` is 376 thousand pages with indexes on subject, entity, lei and the key only; none on `source_code`.

## Parts

- [x] Measure where the time goes: links 21 min, ids lookup one random read a row. 2026-11-19 16:17 ET
- [x] Measure the finish by phase on the finished stores: refresh-ids 15 tables 48 s after the fix (over an hour before); links build 681 s warm (read 79, claims 14, bound ends 151, master states 102, project 273, land 42). 2026-11-19 16:17 ET
- [x] Check that a merged-away master's id still resolves to its survivor: `tests/integration/test_silver_writer_postgres.py::test_refresh_fills_ids_of_rows_already_landed_and_leaves_a_merged_ids_row_to_resolve` asserts both old ids resolve to the survivor through `reads.master`. 2026-11-19 16:17 ET
- [x] Failing test first: `tests/silver_storage/test_delivery.py::test_a_refresh_asks_for_and_writes_only_rows_with_an_empty_id` failed with "assert [['invented-a', 'invented-b']] == [['invented-b']]" (it asked for the key of a row that had an id). 2026-11-19 16:17 ET
- [x] Fix (KISS, operator: "Do not over engineer use kiss"): `link_keys` reads only rows whose id is empty and `set_ids` writes only those; 27 delivery tests pass on PostgreSQL and MySQL. 2026-11-19 16:17 ET
- [x] Prove the refresh on the real stores: 15 tables in 48 s, 1,072 rows filled, no other row written. 2026-11-19 16:17 ET
- [ ] The links build: 681 s warm (about 21 min cold) against a five-minute finish. The projection (one Rust call over 287,530 links) is 273 s of it; the operator decides whether links leave the finish budget or are made incremental
- [ ] Merge the PR when CI is green
- [ ] Learning → skill: data-operations `HOSTED-LOADS.md` (the finish budget and how it is met)
