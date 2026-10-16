# A large CSV or TSV is read in pieces

Priority: 89, tier 1. Map: [Rebuild priorities](../map.md).

Type: task (engine). Status: in progress (branch `claude/csv-streaming`). Blocked by: 86 (CSV and TSV are read the same way).

## Why

Found in ticket 86, onboarding N-PORT (ticket 79). With TSV read as CSV, the engine reads a delimited table whole: `formats::csv` holds every row in memory as a record tree before projecting any. N-PORT's holdings table is 910 MB and 5,347,870 rows (`FUND_REPORTED_HOLDING.tsv`; `IDENTIFIERS.tsv` is 255 MB and 6,749,117 rows). Read whole on this 8 GB machine, the process was killed by the system twice, after 159 s and 266 s (peak resident 1.7 and 2.1 GB, no error from Python). Operator, 2026-10-14: "i told you to not to have caps"; ticket 83 made large outputs write in pieces, but a large delimited input still has to fit in memory.

The engine already streams two framings into private partitions (`source.read` with `read.stream`, `edgar_warehouse/workers/source_stream.py`): `json_array` and `xml_records`. A delimited file is the simplest framing of all: one record per line after the header.

## What changes

- `read.stream.framing: delimited` for `format: csv` and `format: tsv`: the header is read once, then each line is projected as one record through the ordinary contract and written to partitions as the other framings do; the ZIP member is read as a stream, never whole; the same bounds (`max_record`, `partition_records`, `max_partitions`, spool) and refusals (a row with another field count, an encoding failure) as reading whole.
- Reading whole stays for small tables.

## Checklist

- [x] The operator's word to code it: "yes code ticket 89, merge 984 986 987 when green" (2026-10-15 07:06 ET)
- [ ] ~~GoF consult before code: `source_stream.py` framings and the Rust delimited reader~~ missed: the code was written first, against CLAUDE.md's hard rule. Run as the review's GoF axis instead; it found the ordinal and context setup copied into three scans, now shared (2026-10-15 07:38 ET)
- [x] Rust: a delimited record reader over a byte stream (header, then one record per line), CSV quoting and TSV none: `delimited_sequence.rs`, `PyEngine.scan_delimited`; 3 new Rust tests and 23 acceptance tests pass (2026-10-15 07:12 ET)
- [x] `source_stream.py`: `framing: delimited` with `delimited: {format, encoding}`; one ZIP member chosen by `read.stream.member` and streamed; indexed lookups allowed (2026-10-15 07:15 ET, tests below)
- [x] Tests: the same rows streamed as read whole (CSV and TSV); a ragged row, bytes, records, record size and encoding refused; a member pattern matching none or two refused; pieces read back and verified. `test_source_stream_worker.py` and the engine tests: 43 pass (2026-10-15 07:15 ET)
- [x] The N-PORT holdings table streamed through the engine's delimited reader (`SourceEngine.stream_delimited`, the call `source.read` makes): 5,347,869 records, 910,272,312 bytes, 290.6 s, peak resident 15 MB (whole: killed at 2.1 GB). 5,347,867 holdings carry a CUSIP column value (2026-10-15 07:20 ET)
- [x] The N-PORT holdings table end to end through the `source.read` worker (ZIP snapshot, member chosen by `read.stream.member`, pieces written, independent verify): 5,347,869 records, 71 pieces, read 273.8 s, verify 326.2 s, `source.output` true, peak resident 154 MB, 10 min 2 s in all (2026-10-15 07:38 ET)
- [x] READING.md: "Configured delimited record framing" (2026-10-15 07:38 ET)
- [x] Three-axis review (Standards, Spec, GoF). Fixed: `max_record` now counts bytes as written and bounds the header; a repeated header name is refused (reading whole keeps both); the three scans share `stream_context` and `emit`; the worker's ragged-row test names its refusal; the windows-1252 BOM difference is documented. Left: per-record memory is bounded by `max_bytes`, not `max_record` (the csv reader holds one record before its size is known); `read.stream.member` serves every ZIP framing; the delimited framing still declares `max_depth`. Path ownership: `crates/source-contract/**`, `source_*.py` and READING.md are Codex's in CLAUDE.md's table; the overlap guard passed (no open Codex work there), as for ticket 86. Commit f3680025; Rust 3 + 23, Python 43 pass (2026-10-15 07:38 ET)
- [x] PR #990, CI green, merged 2026-10-15 08:09 ET on the operator's "Yes", answering whether to merge #989 and #990
- [x] Learning → skill: data-platform READING.md, "Configured delimited record framing": a large CSV or TSV streams with `framing: delimited`, one declared encoding, `read.format: json` and `each: .`; a ZIP table is chosen with `read.stream.member` (2026-10-15 07:39 ET)
