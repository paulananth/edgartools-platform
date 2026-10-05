# Configured Company pagination reading

Parent goal: self-sustaining installed Rules/parsing/MDM/custom orchestration and complete old-parser retirement. Base PR #821 head 196b43b6; local qualification only.

- [x] Inspect capture availability, retained page/caller contracts and GoF history. — retained contracts and generic reader/history reviewed; 2026-10-05 06:57 ET.
- [x] Declare a packaged page reader using the existing generic filing primitives and receipt-bound capture context. — pagination.yaml and exact typed reader tests; 2026-10-05 06:57 ET.
- [x] Verify exact typed filing parity, recent plus page combination, receipt verification and refusal behavior. — 60 focused cases and 1,170 finite audit cases passed; 2026-10-05 06:57 ET.
- [x] Qualify captured page data when available; record missing physical capture proof explicitly. — captured-qualification.json: five companies, 71 pages, 166,951 rows, exact typed parity and complete forms; 57.932 seconds; 2026-10-05 06:57 ET.
- [x] Verify the installed bundle and full CI, and obtain independent Standards/Spec review. — installed page trial passed in 97.01 seconds; both reviews closed; CI 37242860002 passed all jobs: 1,731 Python, 77 Rust, one existing xfail, no skips; 2026-10-05 06:57 ET.
- [x] Commit/push/create a reviewable PR with exact scope and remaining gates. — PR #822 exists; final evidence committed here; final-head CI required before readiness; 2026-10-05 06:57 ET.
- [ ] Finish census/catalog/provenance, GLEIF/acquisition/adapter replacement, full installed population/replay and all old-parser deletion.

GoF: the native parallel reader and configured filing expressions already cover the retained page column conversions; a new loader or pattern is unnecessary. The frozen 76,230-main capture set has no page receipts, and a targeted cached-capture path search found no pagination files. Captured pagination proof is now recorded below; live SEC acquisition remains outside local qualification.

- [x] Extend generic combination for bounded list union and natural scalar value ordering; verify missing/null keys, exact typed values, element bounds and failure atomicity. — collect_flat and sort_values regressions passed; both review findings closed; 2026-10-05 06:57 ET.
- [x] Download and pin existing S3 pages only (user authorization 2026-10-04); no SEC requests. — 76 versioned objects with SHA-256 receipts, 29,025,198 bytes; zero SEC requests; 2026-10-05 06:57 ET.

The user explicitly authorized S3 downloads after local cached pagination was absent. Downloaded 76 versioned objects (five main documents and 71 complete declared pages), 29,025,198 bytes from the existing prod bronze bucket. Five same-date groups include all 66 JPMorgan pages. Sample is outside git under clean-mdm/captures/company-pagination-s3-20261004.

Configuration gap reproduced: existing collect returns nested form lists rather than a flat bounded union. collect_flat concatenates one list level; duplicate elements count toward max_rows before deduplication. Optional sort_values requires one exact scalar type and natural ordering. First real-capture replay caught canonical-JSON sorting placing S-8 POS before S-8; corrected to natural scalar ordering with a prefix regression. Review caught unmatched collect_flat producing null; fixed using shared collection-mode membership and unmatched/null/error-mode cases. No custom source parser is added.

## Final qualification and remaining gates

The initial installed page trial failed because the fixture expected grouped text `1,234` to become an integer; the retained safe conversion returns null. The corrected trial proves both valid `1234` and invalid `1,234` through the installed bundle. CI also runs the retained Company main and 13F trials.

Captured byte coverage is qualified, but producer provenance and full Company mastering remain explicitly false in the report. The parent retirement item above stays unchecked. PR closeout requires rebasing onto current main, final-head CI and marking ready; no merge or deployment is included.
