# Configured Company pagination reading

Parent goal: self-sustaining installed Rules/parsing/MDM/custom orchestration and complete old-parser retirement. Base PR #821 head 196b43b6; local qualification only.

- [ ] Inspect capture availability, retained page/caller contracts and GoF history.
- [ ] Declare a packaged page reader using the existing generic filing primitives and receipt-bound capture context.
- [ ] Verify exact typed filing parity, recent plus page combination, receipt verification and refusal behavior.
- [ ] Qualify captured page data when available; record missing physical capture proof explicitly.
- [ ] Verify the installed bundle and full CI, and obtain independent Standards/Spec review.
- [ ] Commit/push/create a reviewable PR with exact scope and remaining gates.
- [ ] Finish census/catalog/provenance, GLEIF/acquisition/adapter replacement, full installed population/replay and all old-parser deletion.

GoF: the native parallel reader and configured filing expressions already cover the retained page column conversions; a new loader or pattern is unnecessary. The frozen 76,230-main capture set has no page receipts, and a targeted cached-capture path search found no pagination files. Captured pagination proof remains open; no live SEC acquisition is authorized by local qualification alone.

- [ ] Extend generic combination for bounded list union and natural scalar value ordering; verify missing/null keys, exact typed values, element bounds and failure atomicity.
- [ ] Download and pin existing S3 pages only (user authorization 2026-10-04); no SEC requests.

The user explicitly authorized S3 downloads after local cached pagination was absent. Downloaded 76 versioned objects (five main documents and 71 complete declared pages), 29,025,198 bytes from the existing prod bronze bucket. Five same-date groups include all 66 JPMorgan pages. Sample is outside git under clean-mdm/captures/company-pagination-s3-20261004.

Configuration gap reproduced: existing collect returns nested form lists rather than a flat bounded union. collect_flat concatenates one list level; duplicate elements count toward max_rows before deduplication. Optional sort_values requires one exact scalar type and natural ordering. First real-capture replay caught canonical-JSON sorting placing S-8 POS before S-8; corrected to natural scalar ordering with a prefix regression. Review caught unmatched collect_flat producing null; fixed using shared collection-mode membership and unmatched/null/error-mode cases. No custom source parser is added.
