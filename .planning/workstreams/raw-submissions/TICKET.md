# Raw submissions through configured reading

Full goal: self-sustaining skills, bundled Rules creator, parsing/MDM/custom orchestration and complete old-parser retirement. Continue ticket 20 L4/L5 from open PR #815, in a dedicated Codex worktree. No hosted activation or source approval is inferred.

- [x] Inspect source rules, classification, raw provenance and code history; GoF review. Verified generic classification remains policy-owned; native enums/functions retained; 2026-10-04 09:11 ET.
- [x] Preserve nested JSON values and scalar types through a generic native value expression, with explicit format/range/path safety. Verified 66 Rust tests and focused Python raw values; 2026-10-04 09:11 ET.
- [x] Allow configured preparation to select an object-valued record column, preserving source bodies and rejecting invalid shapes before writing. Verified native binding, worker/verifier immutable round trip and null/list/scalar refusal before output; 2026-10-04 09:11 ET.
- [x] Add Person raw read block; prove complete records and identical governed assertions/IDs/deferrals on pinned captures. Verified qualification.json: 1,000 complete records, 386 identical Person assertions/IDs, 447 entity-undetermined and 167 deferred outcomes; all 14 raw Company columns match. Company joins/grouping remain required; 2026-10-04 09:12 ET.
- [x] Delete Person fixture conversion after retaining its exact assertions from a raw fixture; keep distinct Company/Person/relation/recovery gates. Compared four complete assertions with retained code at07cd4ef0: SHA256 35220d0129283863f957b93fee8317c4ce9ec390003d57d74d52e3709c29640c; regression retained; 2026-10-04 09:11 ET.
- [ ] Prove installed raw reading→preparation→MDM with restricted PG16 roles; native, affected tests, independent reviews and complete CI; create PR.
- [ ] Complete Company reference joins/grouping, GLEIF bounded streaming/three members, adapters mapping replacement and configured acquisition; delete every old parser/caller only after complete source equivalence and installed full-population replay.

Design: retain functions and native enums. Structured values extend the existing native value type; they are not a source-named reader or callback. Person classification remains the pinned Mastering Policy. Record-column selection is explicit worker input configuration, so its verifier reproduces the same complete record rather than guessing an unwrap.
