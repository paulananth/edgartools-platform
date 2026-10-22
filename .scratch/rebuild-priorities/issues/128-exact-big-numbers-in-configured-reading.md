# 128: Exact big numbers in configured reading

Priority: 128. Map: [Rebuild priorities](../map.md). Raised by ticket 40
(2026-10-22), operator: "Exact big numbers in the reader".

Type: task. Status: done (2026-10-22 06:55 ET; merged as #1129, 07:05 ET). Blocked by: none. Blocks: 45.

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

- [x] GoF consult on the engine's number reading, and the overlap guard: `value.rs` has 2 commits in its history, no axis of repeated change; one flag through `scalar` and `element` (2026-10-22 06:45 ET)
- [x] Declared option in the contract; default stays a refusal: `value` gains `big_numbers: refuse | text`, default `refuse`; any other word refuses the contract (2026-10-22 06:55 ET)
- [x] Tests, one per number kind: beyond unsigned 64-bit, thirty digits, large negative, each at the path and inside a list of objects; an unsigned 64-bit stays a number; `type: integer` and `type: number` accept the text, a text value is not a number; default and explicit `refuse` unchanged; `crates/source-contract/tests/value.rs`, 33 engine test groups pass (2026-10-22 06:55 ET)
- [ ] ~~A decimal beyond double precision~~ not a case: a float beyond double range is refused by the JSON parser (`malformed`) before any column reads it, whatever the policy, and a float within range reads as a double, as Python's `json` does; asserted in the same test (2026-10-22 06:55 ET)
- [x] READING.md documents the option ("Complete JSON records") (2026-10-22 06:55 ET)
- [x] Ticket 40's trial contract reads all 368 captured files with the option: 75.7 s; facts 5,134,979 and concepts with facts 139,524, both equal to the long-form copy (2026-10-22 06:55 ET)
- [x] Three-axis review: GoF "leave it"; Standards: a misleading code comment removed, a guide sentence reworded; Spec: streamed JSON arrays still refuse while framing, now stated in READING.md (company facts is a whole-document read) (2026-10-22 06:55 ET)
- [x] PR [#1129](https://github.com/paulananth/edgartools-platform/pull/1129), CI green, merged 2026-10-22 07:05 ET
- [x] Learning → skill: `skills/data-platform/READING.md` (the option) and `skills/company-financials/SKILL.md`, "Reading company facts" (declare it on `units`) (2026-10-22 06:55 ET)
