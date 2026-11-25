# 02: A CSV row of the wrong width is set aside, not the whole file

Status: open
Type: task
Blocked by: none
Blocks: [01](01-implement-current-model-hosted-adv-private-fund-load.md), March's IA private funds

Operator, 2026-11-24 19:30 ET: "Code: set the row aside (Recommended)", asked whether the engine should set aside a row of the
wrong width (counted and reported with its reason, off by default, turned on by a reading) or March's IA funds should
wait.

## Why

March's Form ADV `IA_Schedule_D_7B1` has 3 rows of 68,256 with a stray quote mark, so each reads as 30 fields of 38
(measured with Python's CSV reader; counts only). The engine's CSV reader (`crates/source-contract/src/formats.rs`,
`delimited`, the `csv` crate with `flexible` off) refuses the whole artifact on such a row (`malformed`), so none of
March's 63,746 IA private funds can be read. June's tables are clean.

## What

- A reading declares `read.on_wrong_width: set_aside` (CSV and TSV only; absent means today's refusal). A row whose
  field count differs from the header's is not read as a record: it is set aside in the source extract's deferred
  rows with the reason `wrong_width` and its ordinal, as a row a check sets aside is, and every table of the
  reading counts it.
- Every other malformed shape (an unclosed quote at the end, invalid bytes) still refuses the artifact.
- `reported-csv.yaml` (sources/iapd.adv.fund) turns it on.

## Checklist

- [ ] GoF consult on `formats.rs` / `lib.rs` `document` and the deferred rows (CLAUDE.md, Code review)
- [ ] Test first: a CSV with one short row refuses today (`malformed`), and with `on_wrong_width: set_aside` reads
      the other rows and sets that one aside with `wrong_width`; a row with an unclosed quote still refuses
- [ ] Implement, and the Python binding's reading reports the deferred rows
- [ ] The reading of March's real file: 68,253 rows read, 3 set aside (counts only)
- [ ] Re-add the March step `adv-funds-03` to `rules/load-jobs.yaml` (lane C, after `adv-funds-06`'s sibling order) and its answer in `tests/unit/test_load_jobs.py`
- [ ] Learning → skill: data-platform READING.md, the CSV section, names the option
