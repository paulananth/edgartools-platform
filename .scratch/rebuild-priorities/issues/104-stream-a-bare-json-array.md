# Stream a bare JSON array

Priority: 104, tier 2. Map: [Rebuild priorities](../map.md).

Type: task (code, engine). Status: in progress. Blocked by: none. Blocks: 80 (Onboard OpenFIGI with the skills).

## Why

The OpenFIGI rulings of 2026-10-17 (ticket 80) need, for each identifier asked:
- its one share-class FIGI;
- its one US composite FIGI and that composite's ticker;
- the FIGI and ticker of its only listing, when it has one listing.

Every listing also lands in silver, linked to the Security.

Each of these is a count or member over the identifier's listings (`source.combine` reduce, `members` with `sample_limit: 1`, then a join `where: {count: 1}`, as `issuer-reduce.yaml` does). That needs one row per listing that names its identifier.

An answer names no identifier. It is tied to its request only by its position in the file (`batch:position`, the pair set of `figi-requests.yaml`). The reading grammar cannot give a listing row that position today:
- `each: item` gives one row per answer, with its position. Its listings are only reachable as a list (`pluck`), with no way to count distinct values or pick one by a condition.
- A path through the nested lists gives one row per listing, but `ordinal` is then the listing's place in the whole file, not its answer's.
- The streamed form gives exactly this: each answer a record, `ordinal_context` its one-based position, and `each: data` its listings. But a stream takes only "one object containing one named array" (`json_sequence.rs`: `wrapper` is required and non-empty), and every OpenFIGI answer file is a bare array.

**Minimal failing example** (invented values). The file is `[{"data":[{"figi":"F1"},{"figi":"F2"}]},{"warning":"No identifier found."},{"data":[{"figi":"F3"}]}]`. The wanted rows are `(1,F1)`, `(1,F2)` and `(3,F3)`. No configured reading gives the `1` and the `3`.

## What changes

- `read.stream.wrapper: null` streams a document that is a bare top-level array, one record per element. Everything else stays as it is: the bounds, `ordinal_context`, partitions, EOF and trailing-data refusals, and the verifier's replay.
- A named wrapper keeps its current checks: an extra key or a different name still refuses.
- Nothing else changes.

## Checklist

- [x] The operator's word to code it: "Code 104 (Recommended)" (2026-10-17 08:59 ET)
- [x] GoF consult before code: leave it. `Envelope` (the wrapper object) and `Records` (the array) are already separate, so no wrapper reads `Records` directly; an optional branch, not a structural problem (2026-10-17 09:16 ET)
- [x] `wrapper: null` streams a root array; tests: rows and `ordinal_context` per element, a nested `each` keeps its element's position, an object root refuses when no wrapper is declared, an array root refuses when a wrapper is declared, trailing data and bounds as before. Rust `a_bare_array_streams_when_no_wrapper_is_declared`, Python `test_a_bare_array_streams_when_no_wrapper_is_declared` and the worker test `test_a_bare_array_streams_each_element_with_its_position` (rows (F1,1), (F2,1), (F3,3), verifier replay equal, a wrapped document refused); every Rust test and 181 engine tests pass (2026-10-17 09:16 ET)
- [x] READING.md, "Streamed JSON record projection": the bare-array form (2026-10-17 09:16 ET)
- [ ] Three-axis review (Standards, Spec, GoF)
- [ ] PR, CI green, merge on the operator's word
- [ ] Learning → skill
