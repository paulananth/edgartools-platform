# Rename the SEC Company source identity

## Checklist

- [x] Inventory the source ID, Dataset Contract IDs, filesystem locations, runtime callers, catalog references, and persisted evidence; `git grep` found 198 references in 80 files, and the read-only code/config review identified MDM and Bookkeeping identity records plus OpenMetadata reconciliation as follow-up state (2026-10-31 21:30 ET).
- [x] Rename the active source folder and source ID to `sec.company`; rename its Dataset Contract IDs to `sec.company.v1` and update all active Rules, code, tests, skills, and operational docs (active source tree, source sequence, Bookkeeping, MDM, lineage, qualification scripts, tests and docs reviewed; 2026-10-31 21:33 ET).
- [x] Preserve historical run/capture evidence as historical; document any required local-store or OpenMetadata reconciliation without changing persistent state outside the approved path (dated research content, retired outcome fixtures, historical mapping lists and immutable migration retained; research link points to the renamed current path; local stores and OpenMetadata not changed; reconciliation remains a follow-up; 2026-10-31 21:33 ET).
- [x] Verify no active source/config/runtime reference remains under the old IDs; changed YAML parses, source/folder/Dataset Contract/sequence bindings agree, the nine-sheet Mapping Document has zero old IDs and 67 new-ID cells, and `git diff --check` passes. Remaining old IDs are only immutable or retired historical evidence (2026-10-31 21:34 ET).
- [ ] Run the focused affected project checks; local test execution is deferred because this session's instruction prohibits running tests unless explicitly requested. Await PR CI.
- [x] Create and publish a ready (non-draft) PR: https://github.com/paulananth/edgartools-platform/pull/1262, head `6345c47f` (2026-10-31 21:35 ET).
- [x] Learning → skill: `skills/data-onboarding/SKILL.md` now requires coordinated source folder/ID, Dataset Contract, sequence, Bookkeeping, cross-source reference, and Mapping Document updates; retain prior evidence and use normal Rules review/approval (2026-10-31 21:34 ET).
