# 128: Exact big numbers in configured reading

Priority: 128. Map: [Rebuild priorities](../map.md). Raised by ticket 40
(2026-10-22), operator: "Exact big numbers in the reader".

Type: task. Status: open. Blocked by: none. Blocks: 45.

## What is open

The source engine reads JSON numbers as exact signed or unsigned 64-bit
integers or finite floats, and refuses any other number with
`value_number_range` (READING.md, "Complete JSON records"). One of 368 captured
company facts files holds a 20-digit integer, so the whole file is refused.

Add a generic, declared way for a `value` (and `text`) expression to keep a
number outside that range exactly, as decimal text, never rounded. It is a
generic engine capability (`crates/source-contract/**`), configured per
contract, with no source names in the engine.

Outside standards (research 02 section 4): RFC 8259 section 6 lets a JSON
reader limit number range and precision; RFC 7493 (I-JSON) advises staying
within IEEE double. Exact readers keep the number's text (serde_json's
`arbitrary_precision`, Python's `json` integers). Snowflake keeps a number of up
to 38 digits exactly.

## Checklist

- [ ] GoF consult on the engine's number reading, and the overlap guard
- [ ] Declared option in the contract; default stays a refusal
- [ ] Tests: one per number kind (beyond signed 64-bit, beyond unsigned 64-bit, large negative, a decimal beyond double precision), and the default refusal unchanged
- [ ] READING.md documents the option
- [ ] Ticket 40's trial contract reads all 368 captured files with the option
- [ ] Learning → skill
