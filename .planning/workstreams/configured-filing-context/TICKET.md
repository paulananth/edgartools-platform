# Configured artifact context and filing bounds

Continue ticket 21 after configured content fields (#810). This is design and inventory work until the implementation and tests below pass. Do not retire readers or activate source Rules.

- [x] Inspect retained loader, configured worker, engine facade/native dispatch and git history. Verified caller-supplied CIK/provenance and existing immutable worker receipts; 2026-10-03 18:38 ET.
- [x] GoF review: keep functions and existing worker/engine boundaries. History shows additive language changes; no demonstrated benefit from a new class hierarchy. Verified code/history and reviewer guidance; 2026-10-03 18:38 ET.
- [ ] Declare generic typed artifact context in YAML; add a bounded receipt-bound input to the worker while retaining version-1 manifests.
- [ ] Add context expressions without source-specific loader imports, implicit pathname parsing or replacement of original document data.
- [ ] Add configured first-N record bounds; compare zero, positive, negative and unlimited retained-loader behavior before selecting the grammar.
- [ ] Complete the 18-column recent filing contract, including caller CIK, sync_run_id, raw_object_id and load_mode.
- [ ] Test mismatched context/input receipts, types, missing/extra keys, size bounds, tampering, retries and separate verifier reparse.
- [ ] Compare all output columns on pinned receipts and deliberate source/context mutations; record positive and failure differences explicitly.
- [ ] Prove installed worker and PostgreSQL 16 restricted-role execution; document implemented syntax in the bundled skill.
- [ ] Independent Standards/Spec/GoF reviews, PR and unchanged full CI gate.
- [ ] Complete Company/Person classification, reference joins, grouping and source read blocks.
- [ ] Complete GLEIF equivalence and reader retirement.
- [ ] Full installed empty-store proof: 6,414 Companies, 3,052 CIK+LEI and unchanged replay.

## Current evidence

`stage_recent_filing_loader` receives four output values from caller arguments, independently of payload CIK. `source.read` version 1 currently accepts a pinned contract and one or two exact artifact references. The facade reads only bytes and lookup sets. Existing context must not be inferred from a URI or silently taken from the SEC payload. A hash verifies bytes and binding, not the factual correctness or authorization of context; Rules approval and the execution manifest retain those responsibilities.

The old `recent_limit` computes `min(anchor_count, recent_limit)`, then uses Python `range`. Negative values yield no rows; `None` yields full history. Record safety limits and intentional source failures must remain explicit. No implementation/equivalence claim is made for the proposed interface yet.

## Candidate interface to validate

Keep the existing `Engine.read` path. Add an explicit typed scalar context and expression, with exact declared keys and bounded strings. A version-2 worker manifest may name an input receipt plus a separately pinned context document bound to that exact input receipt. Preserve both receipts in output and independently verify them on reparse. Context never changes the parsing format, worker profile, output destination or control ownership. This is a candidate design, not an activated source policy.
