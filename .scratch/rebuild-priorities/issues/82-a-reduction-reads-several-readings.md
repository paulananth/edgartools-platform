# A reduction reads several source extracts

Priority: 82, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md).

Type: task (build, engine). Status: open. Blocks: 79 (Onboard funds and securities with the skills).

## Why

Ticket 79 onboards the Security master from the 13F information tables, one Security per CUSIP (operator, 2026-10-14: "CUSIP and ISIN join"; "A": the Security carries a filed name and class). Measured on the 999 local 13F files (2026-10-14):

- 2,953,581 holding rows read by the configured reading with no refusal (130 s); 908 MB as a source extract.
- A `source.read` unit holds at most 512 files and 128 MiB of output, so the set needs about 8 units.
- One record per CUSIP per filing (`mdm.prepare` `distinct_on`) is 1,754,997 records for the Merge Stage. One record per CUSIP over the whole set is 29,942.
- Only a reduction (`source.combine` `reduce`, streaming, Rust) can group the whole set by CUSIP within its limits. But a reduction group reads one source extract (`source: String` in `crates/source-contract/src/reduction.rs`, one name in `edgar_warehouse/workers/source_reduction.py`), while a materialized `combine` group already takes a list of 1 to 8.

## What changes

- A reduction group's `source` is one name or an ordered list of 1 to 8 distinct names, as in `combine`. Its order changes no result: counts and samples do not depend on order, and `last`, the one column that does, requires one source and one table, since a union has no single source order.
- data-platform COMBINING.md says so.
- Nothing else: limits, modes and output stay as they are.

## Checklist

- [x] The operator's word to code: "yes code ticket 82". 2026-10-14 21:26 ET
- [x] GoF consult before code: two commits on this code (#878, #911), no repeated axis; copy `combine`'s list form. Leave it. 2026-10-14 21:26 ET
- [x] Rust plan and Python selection take a list; `last` refused over a list. 2026-10-14 21:26 ET
- [x] Tests: Rust `a_group_reads_one_source_or_a_list_and_last_needs_one`; Python `test_a_group_reduces_several_readings_as_one` (two readings equal one reading of their rows; `last` over a list refused; empty, repeated and undeclared lists refused); the old form's tests unchanged and passing. 2026-10-14 21:26 ET
- [x] COMBINING.md. 2026-10-14 21:26 ET
- [x] Affected tests locally: tests/engine (914) with the rebuilt engine, Rust reduction tests (5). Three-axis /code-review: a malformed source list crashed instead of being refused (fixed, tested); the two-line `_sources` copy kept (importing combine would be circular); two reading names for one receipt would double a count reduction, as in combine (noted). GoF: leave it. 2026-10-14 21:29 ET
- [x] PR #978, CI green, merged on the operator's word ("merge 978 and code ticket 83", merge `b295e994`). 2026-10-14 21:37 ET
- [x] Learning → skill: data-platform COMBINING.md (a reduction over several reading units). 2026-10-14 21:29 ET
