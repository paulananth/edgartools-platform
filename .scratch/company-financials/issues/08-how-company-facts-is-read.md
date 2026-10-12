# 08 How company facts is read: configured reading or custom step

Type: grilling. Status: open. Blocked by: 05. Map: [map](../map.md).

## Question

Company facts holds each concept as an object key (`facts.<taxonomy>.<concept>.units.<unit>[]`). Can the source engine's configured reading turn object keys into values (taxonomy, concept, unit columns), or does it need a new engine primitive (Codex's path, `crates/source-contract/**`: a GoF consult, the overlap guard and a request to Codex), or is it a Python custom step (one source alone needs it)? Decide by the runtime responsibility map (`docs/architecture/runtime-responsibilities.md`): generic configured computation in Rust, source-specific code in Python. A contract on one captured file first.
