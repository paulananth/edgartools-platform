# 08 How company facts is read: configured reading or custom step

Priority: 40, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/08-how-company-facts-is-read.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: grilling. Status: resolved (2026-10-22 06:45 ET, operator rulings below). Blocked by: 37. Map: [map](../../company-financials/map.md).

## Question

Company facts holds each concept as an object key (`facts.<taxonomy>.<concept>.units.<unit>[]`). Can the source engine's configured reading turn object keys into values (taxonomy, concept, unit columns), or does it need a new engine primitive (Codex's path, `crates/source-contract/**`: a GoF consult, the overlap guard and a request to Codex), or is it a Python custom step (one source alone needs it)? Decide by the runtime responsibility map (`docs/architecture/runtime-responsibilities.md`): generic configured computation in Rust, source-specific code in Python. A contract on one captured file first.

## Checklist

- [x] Outside standards researched first (Snowflake `FLATTEN`, PostgreSQL `jsonb_each`, Spark `explode`, jq `to_entries`; JSON number range in RFC 8259 and RFC 7493): research 02 section 4 (2026-10-22 06:45 ET)
- [x] Reading kind (operator, 2026-10-22: "configure only"): configured reading, no custom step, no new iteration primitive (2026-10-22 06:45 ET)
- [x] Trial contract on the captured files: `.scratch/company-financials/research/03-company-facts-trial-contract.yaml`, run over the 368 captured files; 367 read, facts equal the long-form copy (5,107,788), one refused (2026-10-22 06:45 ET)
- [x] The refused file (operator: "Exact big numbers in the reader"): engine ticket [128](128-exact-big-numbers-in-configured-reading.md) opened; ticket 45 now waits on it (2026-10-22 06:45 ET)
- [x] Learning → skill: `skills/company-financials/SKILL.md`, "Reading company facts" (2026-10-22 06:45 ET)

## Answer

1. **Configured reading only** (operator: "configure only"). The company facts reader is a source-extract contract; no Python custom step and no new iteration primitive.
2. **Shape.** The engine's `each.entries` reads one object level, with its key as a value. Company facts nests four levels (taxonomy, concept, unit, list of facts), and a table has one iteration. So the contract has one table per taxonomy (`each.entries` on `facts.<taxonomy>`): one row per concept, with the concept's key and its `units` kept whole as one value. The outside standard composes one level at a time the same way (Snowflake `LATERAL FLATTEN`, PostgreSQL `jsonb_each`).
3. **Units and facts are flattened in silver**, by dbt with Snowflake `LATERAL FLATTEN` over the landed `units` value (the rule that Snowflake writes go through dbt). Ticket 43's silver spec takes this as its input.
4. **A new taxonomy refuses the file.** A `taxonomies` table looks every taxonomy key up in a frozen reference list (`on_missing: error`), so a taxonomy with no table is refused, never dropped. The cohort has nine: dei, ecd, ffd, ifrs-full, invest, rxp, srt, us-gaap, vip.
5. **Measured on 368 captured files** (70.9 s for all): 367 read. Their facts equal the long-form copy exactly (5,107,788). Concepts are 138,987 against 138,868; the 119 more all have no facts (ecd 5, ffd 103, us-gaap 11), so they land and flatten to nothing.
6. **One file is refused** (`value_number_range`): one 20-digit cover-page public float on a 10-K/A. The engine reads exact 64-bit integers and finite floats, and refuses rather than round. Operator: "Exact big numbers in the reader": ticket 128 adds exact reading of larger numbers to the engine, and the build (45) waits on it.
