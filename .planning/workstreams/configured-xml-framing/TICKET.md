# Configured XML framing and complete parser retirement

Continue the full self-sustaining Rules/parsing/MDM/custom orchestration goal on `codex/configured-xml-framing-20261006`, rebased onto current main after merged PR #833. Local qualification only; cached captures and authorized S3 reads supply evidence.

- [x] Implement generic bounded XML framing with configured namespace/envelope names and separate header checks; independently review deliberate namespace/text/declaration faults — 2026-10-06 07:03 ET, nine native cases pass; both independent review axes closed. Namespace allocation fault now refuses after 2,112 bytes rather than reading 10,980 bytes, independently confirmed.
- [x] Wire XML framing through the native configured interpreter, Python facade and private worker publication boundary — 2026-10-06 07:03 ET, 389 non-installed engine cases pass including 11 XML worker cases; Spec independently confirmed empty invalid/deferred header and PI refusal publish no outputs.
- [ ] Bundle contracts for all three GLEIF members and both formats, including approved scope and input-bound metadata; qualify full archive counts, hashes, CRC, EOF and selected records against historical results.
- [x] Qualify installed XML parse→prepare→merge with restricted PostgreSQL 16 — 2026-10-06 07:06 ET, final implementation 7d549657 passed in 147.07 seconds, one case and no skips. All 111 native cases also passed. Rebase preserves the implementation files byte-for-byte.
- [x] Run the full CI gate before merging PR #834 — 2026-10-06 20:26 ET, CI 37551604093 passed all jobs on 22c7e922; PR #834 merged as 716cb999 at 20:26 ET.
- [ ] Qualify installed XML publication refusal and recovery with restricted PostgreSQL 16 — continued in gleif-member-contracts/TICKET.md; the installed successful mastering trial above does not prove all failure/recovery modes.
- [ ] Replace active GLEIF consumers; delete old parser implementations and dependencies after full proof.
- [ ] Replace Company preparation/provenance/census/cascade routes and prove installed empty-store 6,414 Company / 3,052 CIK+LEI population plus unchanged replay and recovery.
- [ ] Reconcile actual Claude/Codex completion trackers and retire remaining parser code, adapters and fixtures according to parent issue 20 L3-L8.

GoF/history review: the current generic XML reader and source-specific GLEIF parser differ in namespace, envelope and leading-text behavior. A bounded record scanner with first-class header/record callbacks exposes the needed validation seam without source-specific strategy classes. Keep domain assertions and publication policy in configuration and workers. Existing reader history shows stable interpreter functions; no hierarchy refactor is justified.

The initial generic native scanner is under review and is not a runtime replacement yet. It bounds raw expanded bytes, per-record buffering, encoded records, count and depth; namespace bindings are normalized and scoped per frame; header/record callbacks prepare evidence; complete EOF is required for a receipt. Independent reviews exposed malformed XML acceptance and escaped namespace differences, and deliberate regression cases cover their corrections. Full captured XML parity remains required.

Installed XML parse→prepare→merge trial passed at e25200aa: one case, 24 deselected, no skips, 131.82 seconds on fresh PostgreSQL 16 with restricted roles. The subsequent incremental namespace-size correction requires qualification at its final committed head and full CI before the qualification part above is checked. Complete captured GLEIF XML parity and runtime adoption remain unfinished.

PR #833 merged as 337e737e. On the operator merge instruction, #834 rebased cleanly onto main e4009a9c; final CI is required before merging #834. Full parent goal remains incomplete.

Merged #834 after all CI checks passed. The original full goal remains active; remaining work continues on codex/gleif-member-contracts-20261006 from main 716cb999.
