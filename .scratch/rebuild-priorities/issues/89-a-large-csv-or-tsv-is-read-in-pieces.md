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
- [ ] GoF consult: `source_stream.py` framings and the Rust delimited reader. Not run before the code was written (a miss); run as the review's GoF axis instead
- [x] Rust: a delimited record reader over a byte stream (header, then one record per line), CSV quoting and TSV none: `delimited_sequence.rs`, `PyEngine.scan_delimited`; 3 new Rust tests and 23 acceptance tests pass (2026-10-15 07:12 ET)
- [x] `source_stream.py`: `framing: delimited` with `delimited: {format, encoding}`; one ZIP member chosen by `read.stream.member` and streamed; indexed lookups allowed (2026-10-15 07:15 ET, tests below)
- [x] Tests: the same rows streamed as read whole (CSV and TSV); a ragged row, bytes, records, record size and encoding refused; a member pattern matching none or two refused; pieces read back and verified. `test_source_stream_worker.py` and the engine tests: 43 pass (2026-10-15 07:15 ET)
- [x] The N-PORT holdings table streamed through the engine's delimited reader (`SourceEngine.stream_delimited`, the call `source.read` makes): 5,347,869 records, 910,272,312 bytes, 290.6 s, peak resident 15 MB (whole: killed at 2.1 GB). 5,347,867 holdings carry a CUSIP column value (2026-10-15 07:20 ET)
- [ ] READING.md; three-axis review; PR, CI green, merge on the operator's word
- [ ] Learning → skill
