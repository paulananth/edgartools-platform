# CSV and TSV are read the same way

Priority: 86, tier 1, in flight (raised by the operator, 2026-10-15). Map: [Rebuild priorities](../map.md).

Type: task (engine). Status: claimed (Claude, 2026-10-15 ET, branch `claude/tsv-reading`). Blocked by: none.

## Why

Found onboarding N-PORT (ticket 79): the SEC publishes the N-PORT data set as a ZIP of 30 tab-separated tables (the holdings table alone is 910 MB, 5,347,870 rows), and the source engine read CSV with commas only (`crates/source-contract/src/formats.rs`), so it refused every N-PORT table. The profiler already read TSV as CSV. Operator, 2026-10-15: "csv and tsv must be treated the same".

## What changes

- `read.format: tsv`: a header line, then one record per line, split on tabs; everything `csv` accepts works for it (`encoding`, `container: zip` with `member`, limits, refusals).
- A tab never occurs inside a TSV value, so TSV has no quoting: a quote mark is an ordinary character (the N-PORT holdings table holds none, and no row with another field count).

## Checklist

- [x] GoF consult: the format dispatch (`lib.rs` `document`) gains one branch; leave its shape (four branches, a new format added once a year) 2026-10-15 06:51 ET
- [x] `formats.rs`: `csv` and `tsv` share one delimited reader; `lib.rs`: `tsv` in the formats, its dispatch, its encodings 2026-10-15 06:51 ET
- [x] Test: the same rows from CSV and TSV; a quote mark kept; a ragged row refused; windows-1252; a ZIP member (`cargo test --test acceptance`: 23 passed) 2026-10-15 06:51 ET
- [x] READING.md: TSV beside CSV 2026-10-15 06:51 ET
- [ ] ~~The N-PORT holdings table read through the engine~~ deferred to ticket 89 (a large CSV or TSV is read in pieces): read whole, the 910 MB member was killed by the system after 159 s and 266 s on this 8 GB machine (peak resident 1.7 and 2.1 GB, no error from Python); the reader holds every row in memory, as it does for CSV
- [x] Three-axis review 2026-10-15 06:59 ET: GoF leave (the format list grew once in its life). Spec: the profiler wrote a TSV input's format as `csv`, so a contract written from its findings would split on commas: fixed, findings now declare `tsv` (test in `test_profiling_inputs.py`). Standards: the overlap guard ran before every commit and push (no overlap; `crates/source-contract/**` and READING.md are Codex's paths, taken on by the operator's words); a test value replaced with a neutral one; the bare `quoting` flag left (private, two callers)
- [x] PR #986, CI green, merged by the operator 2026-10-15 06:59 ET (operator, 07:06 ET: "merge 984 986 987 when green")
- [ ] The review fix (profiling declares a TSV input `tsv`) missed that merge: its own PR from `claude/tsv-profiling-format`, merge on the operator's word
- [x] Learning → skill: data-platform READING.md, "`format: tsv` reads tab-separated tables exactly as `csv`"; data-profiling: a profiled TSV input is declared `tsv` 2026-10-15 07:07 ET
