# Selected sequence equivalence and full source retirement

Continue the active full skill goal after #813 (dependency, not merged). Separate Codex branch/worktree. Preserve strict defaults and source safety; retained readers remain oracles until full equivalence.

- [x] Inspect the 450-case / 109-difference audit, existing bounds and history; GoF review. Verified current code/history; preserve functions and use an enum for sequence length/indexing; 2026-10-04 08:27 ET.
- [x] Add explicit generic indexed-object and selected-row validation semantics; keep full anchor count/byte safety and strict default validation. Verified 58 Rust tests and 66 focused Python tests; 2026-10-04 08:27 ET.
- [x] Prove the 450-case matrix has no acceptance/output differences, with independent default, count, index, Unicode and limit regressions. Verified failure-audit.json: 450/450 match; full source count and safety remain enforced; 2026-10-04 08:27 ET.
- [ ] Compare all 18 columns on 1,000 pinned captures and test immutable worker/verifier/installed PostgreSQL 16 paths.
- [ ] Update bundled grammar and source status; Standards/Spec/GoF review, full CI and stacked PR.
- [ ] Complete Company/Person read blocks, reference joins, grouping and governed classification; replace landing-parquet preparation and old loaders.
- [ ] Complete GLEIF Level 1, relationships and reporting exceptions on bounded native reading; assertions, IDs, deferrals and refusals equivalent.
- [ ] Replace adapters.py record mapping when every source has a read block.
- [ ] Build configured provider.capture worker and replace sec_client.py; live SEC proof requires the operator permission named in ticket 20 L8. Local qualification remains the authorized environment.
- [ ] Decommission all old source parsers and their active callers after equivalence.
- [ ] Prove installed empty-store 6,414 Companies / 3,052 CIK+LEI plus unchanged replay.

Design: retain functions and enums. Sequence length and indexing are separate facts: Python counts object keys, but integer lookup fails for nonempty JSON objects; empty objects pad as zero-length sequences. Selected validation skips field access only when no row is selected, after checking the full anchor limit/count. All behavior is explicit contract data, with no source-specific branch or control/loader dependency.

Qualification scope remains finite JSON and first-N behavior, not all malformed source equivalence. Arbitrary integer lexemes outside the existing numeric parser range, nonfinite values and unpaired surrogates retain existing parser refusals and require a source-contract decision/audit before retirement. No source Rules activation or cloud deployment is included.

## Verified corpus and reviews

`complete-qualification.json`: 1,000 receipt-pinned captures / 107,197 rows, all 18 columns match the retained reader with the selected-validation contract. `failure-audit.json`: all 450 acceptance/output decisions match. Independent Standards/Spec reviews found no scoped blockers; GoF review retains the procedural/enum structure. Full local engine suite (including the seventh installed trial) and full CI are running/pending.

This change depends on #813, which remains open. CI only runs for PRs targeting main, so the PR targets main with the dependency explicit; review this incremental change from ef08b9ff. Merge #813 first and rebase this change before landing.
