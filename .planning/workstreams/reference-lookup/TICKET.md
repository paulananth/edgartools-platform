# Configured reference lookup toward source retirement

Source: ticket 20 L3/L4 and the full self-sustaining skill goal. Codex owns this worktree. No source approval or cloud deployment.

- [x] Inspect current reader, grammar and history; GoF review. Verified source conversion and engine history; retain functions/native enum, no class hierarchy; 2026-10-04 08:46 ET.
- [ ] Add bounded contract-embedded keyed reference tables and scalar lookup, with explicit missing/type behavior and load-time validation.
- [ ] Add text uppercase/lowercase as explicit configuration for lookup keys, preserving existing defaults.
- [ ] Compare all SEC place codes plus missing/unknown/coercion cases against retained jurisdiction conversion; immutable worker/verifier proof.
- [ ] Run native and affected Python tests, installed parse-to-MDM PostgreSQL trial, independent reviews and complete CI; create PR.
- [ ] Complete Company/Person reading, grouping/classification, GLEIF streaming, mapping replacement, configured capture and full installed replay before old reader retirement.

Design review: current functions and native value enum remain appropriate. Reference data is embedded in the immutable captured contract; it is not read from an ambient mutable file or supplied as an unbound callback. Lookup is exact text-key access; normalization is an explicit nested expression. Reference limits fail at load time, including an empty source. This increment alone does not retire any reader.
