# 236: A reduce's memory is its state, and a reader parses only the tables it uses

Type: task. Status: open. Blocked by: none.

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

- [ ] Measure the baseline: peak memory and time of each N-PORT reduce on 2026q2 (the proof load's sampler)
- [ ] A reduce writes its output group by group: the state of a group is freed as its rows are written, and no
  whole-output copy is made (Rust `finish` drains one group at a time; the pieces are written as they fill)
- [ ] A streamed reading records where each table's rows sit in each piece, and a reader that names its tables
  parses only those (a piece is still read and checked against its hash whole)
- [ ] Measure again on the same input: same output bytes, peak memory and time before and after
- [ ] Learning → skill
