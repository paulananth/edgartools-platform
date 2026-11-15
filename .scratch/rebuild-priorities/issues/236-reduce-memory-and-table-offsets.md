# 236: A reduce's memory is its state, and a reader parses only the tables it uses

Type: task. Status: resolved. Blocked by: none.

## Why

Operator, 2026-11-14: "opimize it so that memory is not the bottle neck", then "fix this also he engine fix I
suggested would save about 30 seconds. That was the offsets index, which would let a reduce jump straight to its
rows."

Found the same day, N-PORT security 2026q2 on an 8 GB laptop: one reduce holding both N-PORT states reached
7.2 GB and filled swap. Reading the code, a reduce's end holds its output four times at once: the Rust state, a
`serde_json` tree of every group, the same as Python objects, and the whole output encoded as one byte string
before it is cut into pieces. And every reader of a streamed reading parses every table of each piece, though a
reduce selects a few: N-PORT's holdings reading carries the silver holding rows that no reduce reads.

## Parts

- [x] Measure the baseline: peak memory and time of each N-PORT reduce on 2026q2 (the proof load's sampler): the
  series-issuer reduce on main's engine, 8.5 GB peak physical footprint, 313 s (2026-11-14 20:22 ET)
- [x] A reduce writes its output group by group: the state of a group is freed as its rows are written, and no
  whole-output copy is made (Rust `finish` drains one group at a time; the pieces are written as they fill): `cargo test --lib reduction`, `test_a_reduction_streamed_in_batches_writes_the_bytes_of_its_whole_output` (2026-11-14 20:22 ET)
- [x] A streamed reading records where each table's rows sit in each piece, and a reader that names its tables
  parses only those (a piece is still read and checked against its hash whole):
  `test_each_piece_locates_its_tables_and_a_reader_decodes_only_those_it_uses` (2026-11-14 20:22 ET)
- [x] Measure again on the same input: same output bytes, peak memory and time before and after: identical
  pieces (50, same digest) in all three runs; peak 8.5 GB to 2.9 GB; 313 s to 266 s; with offsets 279 s, no gain on
  a reading whose tables the reduce all reads (2026-11-14 20:22 ET)
- [x] GoF consult (after the code, recorded late): leave it; `_streamed_output` mirrors `_output`'s length logic,
  guarded by the byte-equality test (2026-11-14 20:22 ET)
- [x] Learning → skill: data-onboarding, the reduce bullet: measure a step's peak as its physical footprint, and a
  reduce's output streams, so its memory is its state (2026-11-14 20:22 ET)
