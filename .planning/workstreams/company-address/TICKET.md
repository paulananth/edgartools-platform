# Configured Company raw address derivation

Parent goal remains self-sustaining bundled Rules creation, parsing/MDM/custom orchestration and complete old-parser retirement. Stacked on #819 (38722173), no activation or deployment.

- [x] Inspect current refs, legacy address extraction/mapping and native expression traversal/history — generic fallback and conditional evaluation missing; GoF review favors functions and shared expression traversal; 2026-10-04 17:52 ET.
- [x] Implement explicit bounded native coalesce and choose expressions with lazy evaluation and complete call validation — 77 native tests and reviewed shared child traversal; 2026-10-04 18:18 ET.
- [x] Verify scalar types, falsey/null distinction, branch refusals, context/reference/feature traversal and default grammar safety — 77 Rust and 57 focused Python cases passed; Spec whitespace mismatch corrected and independently rerun; 2026-10-04 18:18 ET.
- [ ] Configure raw Company business addresses with frozen SEC place reference data; compare retained derivation on representative/adversarial rows and captured population.
- [ ] Verify native Rust, Python worker/verifier receipts, installed orchestration and full CI with no prerequisite skips.
- [ ] Update bundled grammar/instructions and obtain independent Standards/GoF and Spec reviews.
- [ ] Commit/push/create a reviewable PR with exact evidence.
- [ ] Complete Company census/provenance/pagination and full installed population/replay, GLEIF streaming, acquisition and adapter replacement, then delete all old parsers in the parent goal.

Contract: coalesce requires values (1..16 expressions) and skip (null or falsey); first retained typed value or null, evaluation stops at that value. Falsey is null, false, numerical zero, empty string/list/map. choose requires condition/then/else expressions; boolean condition selects branch, null chooses else, other condition types refuse. All calls are validated, including unused branches; only selected calls execute. No Company-specific runtime code or custom steps.

## Measured verification cost

Initial unbatched 1,000-capture pass matched all 1,000 business addresses in 731.674 seconds (12m12); full local engine at 5122ebb9 passed 255/no skips in 611.40 seconds (10m11), preserving all twelve installed modes. These precede the final whitespace correction and paired qualification driver; final evidence remains pending.

An observed setup bottleneck was the two-pass Rules YAML reader on the frozen reference contract: five-run means 0.15191 seconds with SafeLoader and 0.01594 seconds with CSafeLoader, identical parsed values for that contract. Native Engine construction was 0.008 seconds and a small captured address read 0.0009 seconds. This is a contract-load sample, not a CI speedup claim.

- [ ] Use compiled PyYAML backend when available with the existing safe fallback; preserve contract values and refusals, including escaped-surrogate acceptance that libyaml alone rejects.
- [ ] Replay the 1,000-capture comparison with final native whitespace behavior, bounded pairs and physical execution-file hashes; record the actual result.
