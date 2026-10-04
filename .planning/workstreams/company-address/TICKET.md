# Configured Company raw address derivation

Parent goal remains self-sustaining bundled Rules creation, parsing/MDM/custom orchestration and complete old-parser retirement. Stacked on #819 (38722173), no activation or deployment.

- [x] Inspect current refs, legacy address extraction/mapping and native expression traversal/history — generic fallback and conditional evaluation missing; GoF review favors functions and shared expression traversal; 2026-10-04 17:52 ET.
- [ ] Implement explicit bounded native coalesce and choose expressions with lazy evaluation and complete call validation.
- [ ] Verify scalar types, falsey/null distinction, branch refusals, context/reference/feature traversal and default grammar safety.
- [ ] Configure raw Company business addresses with frozen SEC place reference data; compare retained derivation on representative/adversarial rows and captured population.
- [ ] Verify native Rust, Python worker/verifier receipts, installed orchestration and full CI with no prerequisite skips.
- [ ] Update bundled grammar/instructions and obtain independent Standards/GoF and Spec reviews.
- [ ] Commit/push/create a reviewable PR with exact evidence.
- [ ] Complete Company census/provenance/pagination and full installed population/replay, GLEIF streaming, acquisition and adapter replacement, then delete all old parsers in the parent goal.

Contract: coalesce requires values (1..16 expressions) and skip (null or falsey); first retained typed value or null, evaluation stops at that value. Falsey is null, false, numerical zero, empty string/list/map. choose requires condition/then/else expressions; boolean condition selects branch, null chooses else, other condition types refuse. All calls are validated, including unused branches; only selected calls execute. No Company-specific runtime code or custom steps.
