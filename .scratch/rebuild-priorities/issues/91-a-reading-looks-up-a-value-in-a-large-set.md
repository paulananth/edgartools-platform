# A reading looks up a value in a large set

Priority: 91, tier 1. Map: [Rebuild priorities](../map.md).

Type: task (engine). Status: open, waiting for the operator's word to code it.

## Why

Onboarding the Security from N-PORT (ticket 79; operator ruling 2026-10-15: "Two contracts (Recommended)"). A Security keyed by CUSIP carries its ISIN, and an ISIN-only Security carries its issuer name. CUSIP and issuer name sit on the holding row (`FUND_REPORTED_HOLDING`, 5,347,869 rows); ISIN sits on the holding's identifier rows (`IDENTIFIERS`, 6,749,116 rows, about 4.3 million with an ISIN), linked by `HOLDING_ID`.

No configuration can join them on this machine:
- **A reading's lookup set answers membership only** (`select.member`). It is capped at 1,000,000 values per set and 64 MiB in all. A `read.references` table returns a value but is frozen inside the contract.
- **A `select` test cannot pick rows by a pattern** (`truthy`, `null`, `present` and the like), so the holdings cannot be split into shards.
- **A reduction or combine holds its output rows as Python objects** (COMBINING.md). Grouping by holding gives about 5.3 million rows. The whole-file read of the same table was killed at 2.1 GB on this 8 GB machine.

## What changes

- A lookup set may carry a value per key, supplied like today's sets (a lookup receipt): `lookup: {set: <name>, key: <expression>}` returns the key's values, or null.
- Its bounds are declared and raised for this use: values per set and bytes, measured on N-PORT's 4.3 million holding-to-ISIN pairs.
- The set is built from a source extract (the `IDENTIFIERS` reading) and frozen, so the source worker and the verifier read identical data.
- The holdings reading then emits each holding's CUSIP, ISIN and issuer name in one streamed pass, and the reduction groups pairs, not holdings.

## Checklist

- [ ] The operator's word to code it
- [ ] GoF consult: lookup sets in `crates/source-contract` and `source_stream.py`
- [ ] Rust: a lookup set that maps a key to a value, frozen and indexed once; its bounds
- [ ] The set built from a verified source extract; the receipt pinned like today's sets
- [ ] Tests: values returned, a missing key, bounds refused, verify rebuilds the same reading
- [ ] N-PORT holdings with their ISINs, one streamed pass: rows, time, peak memory
- [ ] READING.md; three-axis review; PR, CI green, merge on the operator's word
- [ ] Learning → skill
