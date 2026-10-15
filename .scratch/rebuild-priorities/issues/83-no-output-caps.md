# No output caps: large outputs are written in pieces

Priority: 83, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md).

Type: task (build, engine). Status: open. Blocks: 79 (Onboard funds and securities with the skills).

## Why

Ticket 79's 13F trial (2026-10-14) stopped on size caps, not on the data:

- A `source.read` unit's whole output was refused past 128 MiB, so the 908 MB 13F source extract needed 8 hand-balanced units.
- The reduction read each unit's output through the 32 MiB index bound, and a 112 MB version-1 output was refused ("Control document exceeds its bounded size").
- A reduction's output was capped at 100,000 rows and 32 MiB, so FIGI (56,288 CUSIP and FIGI pairs) was dropped from the Security v1 configuration.
- `source.combine` refused inputs over 32 MiB (64 MiB in all), more than 100,000 rows, and output over 32 MiB; `mdm.prepare` read at most 32 MiB.

The operator: "why are we still having limits 128 mb", then "i told you to not to have caps".

## What changes

- **Outputs are written in pieces, never refused for their size.** A `source.read` or `source.combine` output over 32 MiB is written as content-addressed pieces of at most 8 MiB and 100,000 rows each, behind a version-2 index (the format streamed source extracts already use). The pieces are written before the index. The only size refusal left is one row larger than a piece.
- `source.read` spools each input's reading to a temporary file, so its memory does not grow with the unit.
- `mdm.prepare` reads one input file at a time and writes each records file as it is made. It reads up to 16 GiB and 100,000,000 rows. Batches are still cut at 1,000 records or 1 MiB.
- `source.combine`: inputs up to 16 GiB and 40,000,000 rows, in Python and Rust (it still holds them in memory).
- A reader of pieces bounds only the integers the index states; the per-file ceilings a contract may declare rise to 16 GiB and 100,000,000 records (in memory) and 1 TiB (streamed).
- A reduction's declared ceilings: state 16 GiB, output 10,000,000 rows and 16 GiB (Rust and Python).
- The MDM batch manifest bound grows from 32 MiB to 1 GiB, about two million batches.
- A check of an output written in pieces redoes the step (`confirm` raises Redo); `verify` compares every piece.
- READING.md and COMBINING.md say so.

## Checklist

- [x] The operator's word to code: "merge 978 and code ticket 83"; "i told you to not to have caps". 2026-10-14 21:37 ET
- [x] GoF consult before code: reuse `source_readings`' version-2 partitions (one `pieces` helper both workers call) instead of a second format. Leave the rest. 2026-10-14 21:40 ET
- [x] `source_readings.pieces`; `source_read` and `source_combine` write pieces past 32 MiB; `verify` compares the pieces; `confirm` redoes. 2026-10-14 21:59 ET
- [x] `mdm.prepare` streams one input file at a time; bounds raised. 2026-10-14 21:59 ET
- [x] Reduction ceilings raised (Rust and Python), engine rebuilt; Rust reduction tests pass (5). 2026-10-14 21:59 ET
- [x] Manifest bound 1 GiB. 2026-10-14 21:59 ET
- [x] Tests: `test_a_large_reading_is_cut_into_pieces_that_read_back_whole`, `test_a_large_combination_is_written_in_pieces_that_read_back_whole` (each splits, verifies and reads back equal to the whole output; one row larger than a piece is refused); the old budget tests now assert pieces where a refusal used to be. 2026-10-14 21:59 ET
- [x] READING.md and COMBINING.md. 2026-10-14 21:59 ET
- [x] Three-axis /code-review (Standards, Spec, GoF). Fixed what it found: a combination over 10M rows or 4,096 pieces was written but refused by every reader (reader bounds now only the integers the index states, `PART_ROWS` one constant); Rust `combine_tables` still refused `max_rows` over 100,000 (now 40,000,000); `source_read` held every piece in memory (pieces now go to a write or compare sink as made, one helper pair for both workers); `mdm.prepare` read a whole input twice under 32 MiB and held a single publication's rows (now `source_readings.iter_artifacts` and `limits.iter_batches`); per-file ceilings for the in-memory reader (16 GiB, 100,000,000 records) and the streamed reader (1 TiB, 10,000,000 pieces) raised; stale messages and doc claims corrected. GoF: pieces publish/check shared (done); `iter_artifacts` shared by `load` and `mdm.prepare` (done). Still bounded, on purpose: one row over an 8 MiB piece, one record over 16 MiB (`mdm.prepare`) or `max_record` (streamed). 2026-10-14 22:09 ET
- [x] Affected tests locally with the rebuilt engine: tests/engine, MDM limits and worker artifacts, 946 passed; Rust 8 passed; new test `test_more_pieces_than_the_old_index_limit_read_back_whole` (5,000 pieces, a 200,000-row combination). Postgres integration tests need Docker: CI. 2026-10-14 22:09 ET
- [ ] PR #981 open, CI green (2026-10-14 22:15 ET); merge on the operator's word
- [x] Rerun the 13F trial with this engine; FIGI restored (ticket 79): all 999 files read in 276 s, reduced in 90 s, no refusals; 20,311 Securities, 10,681 with a FIGI. 2026-10-14 22:31 ET
- [x] Learning → skill: READING.md and COMBINING.md ("No output is refused for its size"; a large output is written in pieces). 2026-10-14 22:09 ET
