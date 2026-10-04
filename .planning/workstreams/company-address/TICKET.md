# Configured Company raw address derivation

Parent goal remains self-sustaining bundled Rules creation, parsing/MDM/custom orchestration and complete old-parser retirement. Stacked on #819 (38722173), no activation or deployment.

- [x] Inspect current refs, legacy address extraction/mapping and native expression traversal/history — generic fallback and conditional evaluation missing; GoF review favors functions and shared expression traversal; 2026-10-04 17:52 ET.
- [x] Implement explicit bounded native coalesce and choose expressions with lazy evaluation and complete call validation — 77 native tests and reviewed shared child traversal; 2026-10-04 18:18 ET.
- [x] Verify scalar types, falsey/null distinction, branch refusals, context/reference/feature traversal and default grammar safety — 77 Rust and 57 focused Python cases passed; Spec whitespace mismatch corrected and independently rerun; 2026-10-04 18:18 ET.
- [x] Configure raw Company business addresses with frozen SEC place reference data — all 309 place codes and variants; final 1,000-capture/1,000-address replay matches in 68.806 seconds across 500 worker units, with physical runtime hashes; 2026-10-04 18:26 ET.
- [x] Verify native Rust, Python worker/verifier receipts, installed orchestration and full CI with no prerequisite skips — 77 Rust; 259 installed engine cases in 436.37 seconds; CI 37239513350: 1,684 Python passed, one existing xfail, no skips. Installed run was at 94ca103e, before the tab-only scanner correction; final rebased gate is additionally required before merge; 2026-10-04 18:26 ET.
- [x] Update bundled grammar/instructions and obtain independent Standards/GoF and Spec reviews — no remaining scoped findings; Python control whitespace and YAML tab acceptance/refusals corrected, 49 scanner parity cases independently compared; 2026-10-04 18:26 ET.
- [x] Commit/push/create a reviewable PR with exact evidence — PR #820 rebased onto merged #819 (473f78e6); final report committed with this checklist; 2026-10-04 18:26 ET.
- [ ] Complete Company census/provenance/pagination and full installed population/replay, GLEIF streaming, acquisition and adapter replacement, then delete all old parsers in the parent goal.

Contract: coalesce requires values (1..16 expressions) and skip (null or falsey); first retained typed value or null, evaluation stops at that value. Falsey is null, false, numerical zero, empty string/list/map. choose requires condition/then/else expressions; boolean condition selects branch, null chooses else, other condition types refuse. All calls are validated, including unused branches; only selected calls execute. No Company-specific runtime code or custom steps.

## Measured verification cost

Initial unbatched 1,000-capture pass matched all 1,000 business addresses in 731.674 seconds (12m12); full local engine at 5122ebb9 passed 255/no skips in 611.40 seconds (10m11), preserving all twelve installed modes. These precede the final whitespace correction and paired qualification driver; final evidence remains pending.

An observed setup bottleneck was the two-pass Rules YAML reader on the frozen reference contract: five-run means 0.15191 seconds with SafeLoader and 0.01594 seconds with CSafeLoader, identical parsed values for that contract. Native Engine construction was 0.008 seconds and a small captured address read 0.0009 seconds. This is a contract-load sample, not a CI speedup claim.

- [x] Use compiled PyYAML backend when available with the existing safe fallback — original scanner handles literal-tab documents and compiled-parser errors; 85 Rules cases pass, including three unquoted-tab refusals, three valid quoted/block tab cases and two surrogate cases; 2026-10-04 18:26 ET.
- [x] Replay the 1,000-capture comparison with final native whitespace behavior, bounded pairs and physical execution-file hashes — final qualification.json: 1,000 matched addresses in 68.806 seconds. Earlier compiled-loader replay was 35.356 seconds; these are different local runs, not a controlled CI speed comparison; 2026-10-04 18:26 ET.
