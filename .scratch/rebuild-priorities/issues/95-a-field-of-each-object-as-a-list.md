# The engine takes a field of each object in a list

Priority: 95, tier 1. Map: [Rebuild priorities](../map.md).

Type: task (engine). Status: in progress (branch `claude/field-list`). Unblocks: 79 part 1 (the N-PORT Security's ISIN with OpenFIGI).

## Why

Each OpenFIGI answer holds a list of listings (objects), each with its own FIGI and composite FIGI. `overlap` (ticket 93) compares two lists of text, so each answer's FIGIs must become one list of text. A reading can give the list of objects, or one joined text, but not the list of a field's values. Operator, 2026-10-15: "Open figi rarely changes do not download again fix engine".

## What changes

- `pluck: {value: EXPRESSION, fields: [name, ...]}`: for each object in the list, in order, the text of each named field; a field missing or null is skipped. A null list gives null. An item that is not an object, or a field value that is not text, refuses with `value_type`. 1 to 16 fields; at most 100,000 values.
- Generic: it names no source or kind.

## Checklist

- [x] The operator's word to code it: "Open figi rarely changes do not download again fix engine" (2026-10-15, answering whether to code tickets 94 and 95)
- [x] GoF consult before code: add both plainly, the way existing primitives are; reuse `sequence`'s shape for `concat` and the `project` children loop for `pluck`; no `as_text`, `join.rs` or `value::element` reuse (their meanings differ) (2026-10-15 17:10 ET)
- [x] `pluck` in Rust; tests (fields in order, missing and null skipped, a null list, other types refused, bounds, a nested expression read): `tests/pluck.rs`; all 31 crate test binaries pass (2026-10-15 17:10 ET)
- [ ] READING.md; three-axis review; PR, CI green, merge on the operator's word
- [ ] Learning → skill
