# Configured XML framing and complete parser retirement

Continue the full self-sustaining Rules/parsing/MDM/custom orchestration goal on `codex/configured-xml-framing-20261006`, stacked on PR #833. Local qualification only; cached captures and authorized S3 reads supply evidence.

- [ ] Implement generic bounded XML framing with configured namespace/envelope names and separate header checks; independently review deliberate namespace/text/declaration faults.
- [ ] Wire XML framing through the native configured interpreter, Python facade and private worker publication boundary.
- [ ] Bundle contracts for all three GLEIF members and both formats, including approved scope and input-bound metadata; qualify full archive counts, hashes, CRC, EOF and selected records against historical results.
- [ ] Qualify installed publication refusal/recovery with restricted PostgreSQL 16 and full CI.
- [ ] Replace active GLEIF consumers; delete old parser implementations and dependencies after full proof.
- [ ] Replace Company preparation/provenance/census/cascade routes and prove installed empty-store 6,414 Company / 3,052 CIK+LEI population plus unchanged replay and recovery.
- [ ] Reconcile actual Claude/Codex completion trackers and retire remaining parser code, adapters and fixtures according to parent issue 20 L3-L8.

GoF/history review: the current generic XML reader and source-specific GLEIF parser differ in namespace, envelope and leading-text behavior. A bounded record scanner with first-class header/record callbacks exposes the needed validation seam without source-specific strategy classes. Keep domain assertions and publication policy in configuration and workers. Existing reader history shows stable interpreter functions; no hierarchy refactor is justified.

The initial generic native scanner is under review and is not a runtime replacement yet. It bounds raw expanded bytes, per-record buffering, encoded records, count and depth; namespace bindings are normalized and scoped per frame; header/record callbacks prepare evidence; complete EOF is required for a receipt. Independent reviews exposed malformed XML acceptance and escaped namespace differences, and deliberate regression cases cover their corrections. Full captured XML parity remains required.
