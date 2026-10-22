# 134 Engine: exact decimals in configured reading

Priority: 134, tier 3, product value. Map: [Rebuild priorities](../map.md).

Type: task. Status: open. Blocks: 45 (the company facts reader).

## Why

The operator ruled, 2026-10-22: "For financial projects never use integer's use
only bigint or big decimal", then "Big decimal". The source engine reads a JSON
number with a fraction or an exponent as a double (ticket 128 kept that, "as
Python's `json` does"). The company facts reader (45) found that every decimal
figure of the 368 captured files reaches Python as a float: 323,634 figures.
None loses a digit through the float today (none has more than 15 significant
digits), but the ruling allows no float between the filed text and the stored
value. An invented `0.1000000000000000055511151231257827` came back as `0.1`,
and `12345678901234567.89` as `1.2345678901234568e+16`.

## What

A declared, generic option on the `value` expression, beside `big_numbers`
(ticket 128): `decimals: text` keeps every number with a fraction or an
exponent as its exact JSON digits, a big decimal for the consumer to parse. The
default, `decimals: float`, is unchanged; any other word refuses the contract.
No source names in the engine.

## Checklist

- [x] GoF consult on `crates/source-contract/src/value.rs`: 3 commits in its history, no axis of repeated change; the two number policies now travel as one `Numbers` value through `scalar` and `element`, so a third policy is one field, not a third parameter (2026-10-22 17:56 ET)
- [x] Overlap guard: no overlap at the start (2026-10-22 17:55 ET); the review fix touched `crates/source-contract/src/lib.rs`, which PR #1121 (Codex) also changes. The guard said stop, and a piped `tail` hid its exit status, so the commit was pushed before asking. #1121 adds module lines at the top; #1139 one refusal 230 lines lower, no conflict. Operator: "Go ahead (Recommended)" (2026-10-22 18:08 ET)
- [x] Declared option, default unchanged: `value` gains `decimals: float | text`, default `float`; `decimals: round` refuses the contract (2026-10-22 17:57 ET)
- [x] Tests, one per kind of decimal, each at the path and inside a list of objects beside an integer and a big integer: plain, trailing zero kept, beyond double precision, beyond double digits, small negative, exponent spelling; the default and explicit `float` still give a double; a text value is still not a number; `crates/source-contract/tests/value.rs`, every engine test passes (2026-10-22 17:57 ET)
- [x] READING.md documents the option ("Complete JSON records") (2026-10-22 17:58 ET)
- [x] Ticket 45's contract reads all 368 captured files with the option: 5,134,979 facts, every file equal fact by fact to the file read directly in exact decimals, no figure arrives as a float (`.scratch/company-financials/reader/full_read.py` on ticket 45's branch, 123 s) (2026-10-22 18:02 ET)
- [x] Three-axis review, all findings fixed: GoF "leave it" (the `Numbers` grouping keeps the next option cheap); GoF and Standards: the fraction check made once (`decimal`), the extra comment dropped, READING.md states where the option applies and no longer names a domain skill; GoF: a kept decimal passed `type: integer`, now refused as a float is, tested; Spec: a framed record (streamed JSON array, CSV, XML records) had already parsed its numbers, so `decimals: text` returned a float's digits labelled exact; now the contract refuses there, tested, and `each.entries`, `from: document` and `jsonl` are tested to keep the digits; 33 engine test groups pass, ticket 45's 7 tests pass on the rebuilt engine (2026-10-22 18:07 ET)
- [ ] PR, CI green, merge
- [x] Learning → skill: `skills/data-platform/READING.md` (the option); `skills/company-financials/SKILL.md`, Hard stops (no `integer` or float in financial work: bigint or big decimal) and "Reading company facts" (declare `decimals: text` on `units`) (2026-10-22 17:58 ET)
