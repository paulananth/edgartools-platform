# The engine builds one text from parts

Priority: 94, tier 1. Map: [Rebuild priorities](../map.md).

Type: task (engine). Status: in progress (branch `claude/text-from-parts`). Unblocks: 79 part 1 (the N-PORT Security's ISIN with OpenFIGI).

## Why

OpenFIGI's mapping answer is a list in the order of its request and names no identifier: the answer to the third job is the third item. To match each answer to its identifier, the request reading and the answer reading must build the same key from the batch (a context value) and the job's position (an integer), and the engine has no way to write a number as text or to join texts into one key. Operator, 2026-10-15: "Open figi rarely changes do not download again fix engine".

## What changes

- `concat: [EXPRESSION, ...]`: one text from its parts, in order. A text part is taken as it is; an integer is written in decimal. A null part makes the whole null, so a key with a missing part is never a shorter key. Any other type (float, boolean, list, object) refuses with `value_type`. At most 128 parts; the text is bounded as other text (1 MiB).
- Generic: it names no source or kind.

## Checklist

- [x] The operator's word to code it: "Open figi rarely changes do not download again fix engine" (2026-10-15, answering whether to code tickets 94 and 95)
- [x] GoF consult before code: add both plainly, the way existing primitives are; reuse `sequence`'s shape for `concat` and the `project` children loop for `pluck`; no `as_text`, `join.rs` or `value::element` reuse (their meanings differ) (2026-10-15 17:10 ET)
- [x] `concat` in Rust; tests (text and integers, a null part, other types refused, bounds, a nested expression read): `tests/concat.rs`; all 31 crate test binaries pass (2026-10-15 17:10 ET)
- [ ] READING.md; three-axis review; PR, CI green, merge on the operator's word
- [ ] Learning → skill
