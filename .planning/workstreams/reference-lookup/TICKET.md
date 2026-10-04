# Configured reference lookup toward source retirement

Source: ticket 20 L3/L4 and the full self-sustaining skill goal. Codex owns this worktree. No source approval or cloud deployment.

- [x] Inspect current reader, grammar and history; GoF review. Verified source conversion and engine history; retain functions/native enum, no class hierarchy; 2026-10-04 08:46 ET.
- [x] Add bounded contract-embedded keyed reference tables and scalar lookup, with explicit missing/type behavior and load-time validation. Verified 63 native tests including nested-key exact integer and literal-reference mode regressions; 2026-10-04 08:54 ET.
- [x] Add text uppercase/lowercase as explicit configuration for lookup keys, preserving existing defaults. Verified native/Python cases and unchanged scalar defaults; 2026-10-04 08:54 ET.
- [x] Compare all SEC place codes plus missing/unknown/coercion cases against retained jurisdiction conversion; immutable worker/verifier proof. Verified all 941 cases match and changed reference receipts cannot validate old output; 2026-10-04 08:54 ET.
- [x] Run native and affected Python tests, installed parse-to-MDM PostgreSQL trial, independent reviews and complete CI; create PR. Verified 63 Rust, 58 corrected-binding focused tests; local full engine 177 passed in 321.64s at315c4461, all eight installed trials; corrected head6348ac55 CI37203412633 all five suites/gate passed; reviews fixed two findings then 0 scoped blockers; PR815; 2026-10-04 08:54 ET.
- [ ] Complete Company/Person reading, grouping/classification, GLEIF streaming, mapping replacement, configured capture and full installed replay before old reader retirement.

Design review: current functions and native value enum remain appropriate. Reference data is embedded in the immutable captured contract; it is not read from an ambient mutable file or supplied as an unbound callback. Lookup is exact text-key access; normalization is an explicit nested expression. Reference limits fail at load time, including an empty source. This increment alone does not retire any reader.

## Review corrections

Shared feature detection now traverses only executable expressions, including nested lookup keys. It preserves exact integer lexemes inside custom conversion without letting literal reference cells enable parsing modes. Native counterexamples retain both refusal and positive matches. Corrected-head CI qualifies the installed bundle independently of the earlier local full run. Final documentation-head CI remains the PR landing gate.
