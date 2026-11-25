# 02: A CSV row of the wrong width is set aside, not the whole file

Status: resolved
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

- [x] GoF consult on `formats.rs` / `lib.rs` `document` and the deferred rows (CLAUDE.md, Code review): Haiku, "leave it"; a marker on the record (`El.wrong_width`) is the smallest seam (2026-11-24 20:10 ET)
- [x] Test first: a CSV with one short row refuses today (`malformed`), and with `on_wrong_width: set_aside` reads
      the other rows and sets that one aside with `wrong_width`; a row with an unclosed quote still refuses:
      `tests/acceptance.rs` `a_reading_that_sets_aside_a_wrong_width_row_reads_the_others` failed first with `malformed`;
      its unclosed-quote case was set aside until the guard that refuses a wrong-width record spanning lines; 239
      crate tests pass (2026-11-24 20:10 ET)
- [x] Implement, and the Python binding's reading reports the deferred rows (`SourceEngine.read(...).deferred`, checked
      on the real file below). A streamed reading declares `format: json`, for which the option is refused (2026-11-24 20:10 ET)
- [x] The reading of March's real file: 68,253 rows read, 3 set aside (counts only): refused without the option; with it
      68,253 read and 3 set aside `wrong_width`; June reads the same either way, 13,798 rows, none aside (2026-11-24 20:10 ET)
- [x] Re-add the March step `adv-funds-03` to `rules/load-jobs.yaml` and its answer in `tests/unit/test_load_jobs.py`:
      lane C before `adv-funds-06`, oldest month first as the adviser filings load (a month's revision is its delivery
      date); `reported-csv.yaml` turns the option on; load-jobs, source-sequence and ADV tests 315 passed (2026-11-24 20:10 ET)
- [x] Proof on a disposable store: March then June, adviser filings then funds each month. First run (2026-11-24 20:10 ET): both months'
      adviser filings completed and June's funds loaded (12,624 links), but March's funds stopped: the funds' reduce
      (`source_reduction.py`, "Reduction requires resolved deferred records") and the combine (`source_combine.py`) refuse a
      source extract that has set-aside rows. The reading alone is not enough for a source whose records come from a combine.
      Rerun of March's funds alone after the fix below, on the same store (so March after June, the order the hosted
      reload may meet): complete in 0.8 min; 67,865 Fund Structures, equal to the distinct PFIDs of March's and June's IA
      7.B(1) and 7.B(2); 65,163 advisor, 1,327 subadvisor and 2,759 feeder links; a second March load: 0 documents
      loaded, 1 already loaded (2026-11-24 20:10 ET).
- [x] Reduce and combine take a reading whose only set-aside rows are `wrong_width` (a row whose bytes are wrong can never
      be resolved by a steward); a row a check sets aside still refuses. GoF consult first; test first. Until then
      `adv-funds-03` stays off main: a failed step in lane C would block `adv-funds-06` on the hosted reload.
      Done: `source_readings.unresolved` (reasons set aside for good: `wrong_width`) at the four refusals: reduction,
      combination, derived lookup and derived context. GoF (Haiku): one shared predicate, no pattern. Tests first:
      `test_a_row_set_aside_for_its_width_passes_and_any_other_set_aside_row_refuses` in test_source_reduction.py and
      test_source_combine.py failed with "Reduction requires resolved deferred records" and "Combination requires
      explicitly resolved deferred records"; tests/engine 926 passed (2026-11-24 20:10 ET).
- [x] Learning → skill: data-platform READING.md, the CSV section, names the option and when to use it (measure first;
      many wrong-width lines mean a wrong delimiter or encoding) (2026-11-24 20:10 ET)
