# 08 How company facts is read: configured reading or custom step

Priority: 40, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/08-how-company-facts-is-read.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: grilling. Status: open. Blocked by: 37. Map: [map](../../company-financials/map.md).

## Question

Company facts holds each concept as an object key (`facts.<taxonomy>.<concept>.units.<unit>[]`). Can the source engine's configured reading turn object keys into values (taxonomy, concept, unit columns), or does it need a new engine primitive (Codex's path, `crates/source-contract/**`: a GoF consult, the overlap guard and a request to Codex), or is it a Python custom step (one source alone needs it)? Decide by the runtime responsibility map (`docs/architecture/runtime-responsibilities.md`): generic configured computation in Rust, source-specific code in Python. A contract on one captured file first.
