# Resolve the configured-reading PR conflicts sequentially

Continue the active parser-retirement goal. Resolve and verify branch history; no merge of #827, #828 or #829 is included.

- [x] Inspect live PR/main state and prove the merged #826 tree equals its prior head — 2026-10-05 18:04 ET, #826 merged as 5169930c; git diff e76fb929 origin/main is empty.
- [ ] Rebase #827 after the merged #826 boundary, preserve implementation, verify checks and push with an exact lease.
- [ ] Rebase #828 after the corrected #827 boundary, preserve implementation, verify checks and push with an exact lease.
- [ ] Rebase #829 after the corrected #828 boundary, preserve streaming changes, verify checks and push with an exact lease.
- [ ] Refresh each PR's dependency/evidence notes and confirm GitHub reports no conflicts with current main.
- [ ] Complete configured streaming, GLEIF JSON/XML replacement, MDM preparation/provenance/census/cascade and full installed population/replay/recovery in the parent goal.

The original sibling worktrees are preserved. Active edits use dedicated worktrees under /private/tmp with independent writable Git metadata because current filesystem permissions make the original siblings read-only. Run the overlap guard against both the original repository's runtime worktrees and the current writable worktree before every commit and push.
