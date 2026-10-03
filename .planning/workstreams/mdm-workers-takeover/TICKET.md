# MDM workers takeover

Scope: qualify Claude's four committed MDM worker changes on current main and create a reviewable PR. The remaining Company/GLEIF/Person completion work is outside this slice.

- [ ] Preserve original Claude branch and apply four commits to dedicated Codex worktree.
- [ ] Review worker interfaces, immutable inputs, destination leases, receipts, publication and runtime pinning; fix demonstrated defects.
- [ ] Run affected PostgreSQL 16 and installed-bundle tests with no prerequisite skips.
- [ ] Run unit, architecture and MDM tests.
- [ ] Push and create PR; verify all five CI suites and aggregate gate.

## Design review

The existing registry and function-based worker adapters are appropriate. Recent history shows new profiles added without changes to Bookkeeping control; no additional GoF hierarchy is justified.
