# A reading looks up a value in a large set

Priority: 91, tier 1. Map: [Rebuild priorities](../map.md).

Type: task (engine). Status: in progress (branch `claude/lookup-values`).

## Why

Onboarding the Security from N-PORT (ticket 79; operator ruling 2026-10-15: "Two contracts (Recommended)"). A Security keyed by CUSIP carries its ISIN, and an ISIN-only Security carries its issuer name. CUSIP and issuer name sit on the holding row (`FUND_REPORTED_HOLDING`, 5,347,869 rows); ISIN sits on the holding's identifier rows (`IDENTIFIERS`, 6,749,116 rows, about 4.3 million with an ISIN), linked by `HOLDING_ID`.

No configuration can join them on this machine:
- **A reading's lookup set answers membership only** (`select.member`). It is capped at 1,000,000 values per set and 64 MiB in all. A `read.references` table returns a value but is frozen inside the contract.
- **A `select` test cannot pick rows by a pattern** (`truthy`, `null`, `present` and the like), so the holdings cannot be split into shards.
- **A reduction or combine holds its output rows as Python objects** (COMBINING.md). Grouping by holding gives about 5.3 million rows. The whole-file read of the same table was killed at 2.1 GB on this 8 GB machine.

## What changes

- A lookup set may hold pairs (`pairs: true`): each item a key and its value. It is its own kind in the engine (`LookupSet::Pairs`), so a pair set is never read as a membership set or the other way round.
- `member_value: {lookup, key, on_many}` gives the key's one value; null for an absent or null key; for several distinct values, null (`on_many: "null"`) or a refusal (`on_many: error`). It never chooses one of several. This replaces the first draft's `lookup: {set, key}` returning every value (design, 2026-10-15): a reading column holds one value, and a choice among several would be a guess.
- A derived set (version-2 lookup receipt) names `value_column` beside `column`, so the set is built from a verified source extract and frozen: the source worker and the verifier read identical data.
- Ceilings rise for every lookup set, not only pairs: 100,000,000 values and 16 GiB per set and in all; derived inputs up to 16 GiB and 100,000,000 rows. This follows the operator's "no caps" ruling (2026-10-14, ticket 83): a contract declares its measured bounds under ceilings set by the machine, not by a fixed cap. The inline receipt document stays at most 64 MiB.
- The holdings reading then emits each holding's CUSIP, ISIN and issuer name in one streamed pass, and the reduction groups pairs, not holdings.

## Checklist

- [x] The operator's word to code it: "Code 91 first" (2026-10-15, answering the ISIN-join question)
- [x] GoF consult before code: it replaced a key-and-separator encoding with a two-kind set (`LookupSet`), which also catches `in_lookup` on a pair set (2026-10-15 11:20 ET)
- [x] Rust: a pair set, `member_value`, the kinds checked at load and at read, named ceilings (`lookup_sets.rs`, `lib.rs`, `python.rs`); all crate tests pass, 10 in `tests/lookup_sets.rs` (2026-10-15 11:28 ET)
- [x] The set built from a verified source extract (`value_column` in a version-2 receipt), or given inline as key and value lists (version 1) (2026-10-15 11:28 ET)
- [x] Tests: values returned, a missing key, several values (null or `lookup_many`), bounds refused (Rust; Python inline and derived receipts), a malformed pair item, the kinds never crossed (`member`, `in_lookup`, `member_value`), verify rebuilds the same reading, and the worker's ceiling held equal to the engine's. Rust crate tests pass; 305 Python tests pass (2026-10-15 11:30 ET)
- [x] Scale, on invented data of N-PORT's size, not the provider's data (the run-once rule: N-PORT itself is read once, in the Security test run): 5,347,869 streamed rows, a 4,330,000-pair set, every key found; 329.1 s, peak resident 1.5 GB (2026-10-15 11:28 ET)
- [x] READING.md: "A key's value from a pair set", the new ceilings, `value_column` (2026-10-15 11:30 ET)
- [x] Three-axis review (Standards, Spec, GoF). Fixed: `in_lookup` on a pair set refused at load; `LookupSet::len`; one branch in `indexed_sets`; derived ceilings aliased to the worker's input ceilings and the aggregate held equal to the engine's by a test; Python bound tests; the error text names `pairs` and quoting `"null"`; the ticket's What changes rewritten. Left: membership ceilings raised with pair ceilings (the "no caps" ruling); bounds are counted at four boundaries (receipt, derived build, engine intake, engine check), which guard different things (2026-10-15 11:30 ET)
- [ ] PR, CI green, merge on the operator's word
- [x] Learning → skill: data-platform READING.md, "A key's value from a pair set (a join in one streamed pass)": join a large table to another by key with a pair set, never a materialized combine (2026-10-15 11:30 ET)
