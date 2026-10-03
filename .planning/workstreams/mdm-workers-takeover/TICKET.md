# MDM workers takeover

Scope: qualify Claude's four committed MDM worker changes on current main and create a reviewable PR. The remaining Company/GLEIF/Person completion work is outside this slice.

- [x] Preserve original Claude branch and apply four commits to dedicated Codex worktree — verified git refs and clean original tree; 2026-10-03 16:04 ET.
- [x] Review worker interfaces, immutable inputs, destination leases, receipts, publication and runtime pinning; fix demonstrated defects — exact manifest-scope check, reserved staging path and regression coverage; 2026-10-03 16:04 ET.
- [x] Run affected PostgreSQL 16 and installed-bundle tests with no prerequisite skips — 13 local tests passed in 313.20s, including read-only verifier, lease expiry, lost acknowledgement, artifact safety and installed parse/prepare/merge; 2026-10-03 16:08 ET.
- [x] Run unit, architecture and MDM tests — 1,159 local cases passed in 224.03s; CI also passed all four added artifact regressions; 2026-10-03 16:07 ET.
- [x] Push and create PR; verify all five CI suites and aggregate gate — PR #806; run 37150109865 passed all six jobs; 2026-10-03 16:07 ET.

## Design review

The existing registry and function-based worker adapters are appropriate. Recent history shows new profiles added without changes to Bookkeeping control; no additional GoF hierarchy is justified.

## CI qualification

Run https://github.com/paulananth/edgartools-platform/actions/runs/37150109865 on implementation commit ddd41099:

- Unit: 401 passed; architecture: 251 passed.
- MDM: 511 passed.
- PostgreSQL integration: 257 passed, one pre-existing expected failure (`test_a_record_that_changes_its_cik_is_held_in_review`); zero skips.
- Engine: 18 Python tests and 25 Rust tests passed; zero skips, including installed-bundle parse/prepare/merge.
- All five suites and aggregate gate passed.

Non-Journal export/graph publication retains its local-only sink. No AWS deployment or Rules activation is included. Remaining Company/GLEIF/Person conversion and full empty-store qualification remain in the original completion ticket.
