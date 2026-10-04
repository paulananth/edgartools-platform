# Configured artifact context and filing bounds

Continue ticket 21 after configured content fields (#810). The context interface and filing-column contract are implemented and locally qualified; full source/mastering equivalence remains incomplete. Do not retire readers or activate source Rules.

- [x] Inspect retained loader, configured worker, engine facade/native dispatch and git history. Verified caller-supplied CIK/provenance and existing immutable worker receipts; 2026-10-03 18:33 ET.
- [x] GoF review: keep functions and existing worker/engine boundaries. History shows additive language changes; no demonstrated benefit from a new class hierarchy. Verified code/history and reviewer guidance; 2026-10-03 18:33 ET.
- [x] Declare generic typed artifact context in YAML; add a bounded receipt-bound input to the worker while retaining version-1 manifests. Verified native and Python worker tests passed; 2026-10-04 07:04 ET.
- [x] Add context expressions without source-specific loader imports, implicit pathname parsing or replacement of original document data. Verified 51 Rust tests passed; scoped Standards/Spec reviews; 2026-10-04 07:04 ET.
- [x] Add configured first-N record bounds; compare zero, positive, negative and unlimited retained-loader behavior before selecting the grammar. Verified Rust boundary tests and eight 18-column Python oracle cases passed; 2026-10-04 07:04 ET.
- [x] Complete the 18-column recent filing contract, including caller CIK, sync_run_id, raw_object_id and load_mode. Verified complete-qualification.json: 1,000 distinct filings / 107,197 rows; 2026-10-04 07:04 ET.
- [x] Test mismatched context/input receipts, types, missing/extra keys, size bounds, tampering, retries and separate verifier reparse. Verified focused worker/context tests passed; decoder runtime mutation changes digest; 2026-10-04 07:04 ET.
- [x] Compare all output columns on pinned receipts and deliberate source/context mutations; record positive and failure differences explicitly. Verified corpus artifacts, worker mutation tests and source-shape-audit.json (six unresolved malformed/coercion differences); 2026-10-04 07:08 ET.
- [x] Prove installed worker and PostgreSQL 16 restricted-role execution; document implemented syntax in the bundled skill. Verified 141 engine tests passed in 297.11s including installed fifth context trial; bundled READING.md syntax; 2026-10-04 07:04 ET.
- [ ] Independent Standards/Spec/GoF reviews, PR and unchanged full CI gate.
- [ ] Complete Company/Person classification, reference joins, grouping and source read blocks.
- [ ] Complete GLEIF equivalence and reader retirement.
- [ ] Full installed empty-store proof: 6,414 Companies, 3,052 CIK+LEI and unchanged replay.

## Current evidence

`stage_recent_filing_loader` receives four output values from caller arguments, independently of payload CIK. `source.read` version 1 currently accepts a pinned contract and one or two exact artifact references. The facade reads only bytes and lookup sets. Existing context must not be inferred from a URI or silently taken from the SEC payload. A hash verifies bytes and binding, not the factual correctness or authorization of context; Rules approval and the execution manifest retain those responsibilities.

The old `recent_limit` computes `min(anchor_count, recent_limit)`, then uses Python `range`. Negative values yield no rows; `None` yields full history. Record safety limits and intentional source failures must remain explicit. The new declared limit matches those supported integer/null cases; full malformed source parity is not established.

## Implemented interface

Keep the existing `Engine.read` path. Add an explicit typed scalar context and expression, with exact declared keys and bounded strings. A version-2 worker manifest names an input receipt plus a separately pinned context document bound to that exact input receipt. Preserve both receipts in output and independently verify them on reparse. Context never changes the parsing format, worker profile, output destination or control ownership. This interface is implemented; no active source Rules are changed.

## Qualification and review

- 51 Rust tests; focused context/worker tests; 141 engine tests including installed context trial on PostgreSQL 16 passed.
- Complete 18-column comparison: 1,000 inputs / 107,197 rows. Bounded first-N=1: 100 inputs / 100 rows. Both artifacts pin contract and captured receipt hashes. Caller provenance is explicit qualification context, not a claim to reproduce historic production caller metadata.
- Independent Standards/Spec reviewers: no scoped blockers. JSON context decoding is now included in worker runtime evidence; mutation coverage checks the dependency. Final CI and the full source-failure audit remain pending.
- Full malformed source equivalence remains incomplete: existing text conversion and shape refusal behavior must be assessed before retirement, beyond actual-corpus positive parity.

## Source refusal and coercion audit

Seven deliberate cases were compared with the retained loader. Native float text matched. Six differ: boolean text capitalization, object/list text coercion, null filings/recent groups, and scalar parallel fields. `source-shape-audit.json` records exact inputs and outputs. These remain required follow-ups before loader retirement; the 18-column actual-corpus proof does not cover them.

Initial CI run 37197487468 passed Engine/MDM/Integration/shell and exposed the decoder module import through the parent Bookkeeping namespace. Fixed the import to the explicitly allowed artifact interface, and strengthened the architecture gate to cover both Python import syntaxes. No isolation gate is weakened or skipped.
