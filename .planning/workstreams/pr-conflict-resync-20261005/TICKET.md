# Resolve the configured-reading PR conflicts sequentially

Continue the active parser-retirement goal. Resolve and verify branch history; no merge of #827, #828 or #829 is included.

- [x] Inspect live PR/main state and prove the merged #826 tree equals its prior head — 2026-10-05 18:04 ET, #826 merged as 5169930c; git diff e76fb929 origin/main is empty.
- [x] Rebase #827 after the merged #826 boundary, preserve implementation, verify checks and push with an exact lease — 2026-10-05 18:17 ET, identical implementation tree, 38 focused checks, gate 37380319899 passed on 6735bf67; #827 merged as 389a020e.
- [x] Rebase #828 after the corrected #827 boundary, preserve implementation, verify checks and push with an exact lease — 2026-10-05 18:17 ET, identical tracked tree, 17 focused checks; gates 37380521461 and 37381116168 passed; current 32131bdb is MERGEABLE directly on merged #827.
- [x] Rebase #829 after the corrected #828 boundary, preserve streaming changes, verify checks and push with an exact lease — 2026-10-05 18:20 ET, identical tracked tree after sequential rebase; f2d78b94 pushed, MERGEABLE on current main 389a020e; preceding code-identical head passed gate 37380697576. Final metadata gate must pass before reporting final readiness.
- [x] Refresh each PR's dependency/evidence notes and confirm GitHub reports no conflicts with current main — 2026-10-05 18:24 ET, #827 merged; #828 and #829 MERGEABLE on 389a020e; PR bodies record actual dependency and qualification state.
- [x] Verify the complete final gate after committing the synchronization evidence; keep all suites, restricted PostgreSQL 16 roles and no prerequisite skips — 2026-10-05 18:24 ET, 37381736078 passed on f2d78b94 containing the committed resync ticket; all suites and aggregate gate passed. The final evidence-only commit must also pass before reporting final readiness.
- [ ] Complete configured streaming, GLEIF JSON/XML replacement, MDM preparation/provenance/census/cascade and full installed population/replay/recovery in the parent goal.

The original sibling worktrees are preserved. Active edits use dedicated worktrees under /private/tmp with independent writable Git metadata because current filesystem permissions make the original siblings read-only. Run the overlap guard against both the original repository's runtime worktrees and the current writable worktree before every commit and push.

## Sequential landing evidence

#826 merged as 5169930c; #827 subsequently merged as 389a020e. Rebased #828 again directly onto that main commit (32131bdb); both its earlier and direct-main CI gates passed without implementation changes. #829 was then replayed onto corrected #828, preserving its complete tracked tree before synchronization-note changes. Source/test preservation is proved with git diff against the prior qualified heads, independently of rewritten commit identities.

Main may advance when the operator lands the next parent; refresh it before the final lease-protected push. The configured-streaming/GLEIF/MDM parent objective remains incomplete regardless of these conflict resolutions.
