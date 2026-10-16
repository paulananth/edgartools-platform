# Merge without repeated approval

Operator request: remove the explicit merge-approval requirement from AGENTS.md and CLAUDE.md, then merge ready PRs one at a time.

## Parts

- [x] Update both guides and remove the related instruction to stop for a merge; retained green CI and other approval boundaries (documentation assertions; 2026-10-16 15:12 ET).
- [x] Verify the documentation diff and review Standards, Spec and GoF (two matching edits, no runtime change, whitespace clean; 2026-10-16 15:12 ET).
- [ ] Publish a dedicated PR and verify every CI check is green.
- [ ] Merge this policy PR, then ready PRs #1019, #1016 and #1015 sequentially, checking each PR's current head and CI.
- [ ] Verify the merged guidance and final CI; keep #1017 in draft pending findings approval and MDM lookup proof.
- [x] Learning → skill: project merge policy updated in AGENTS.md and CLAUDE.md; no skill change needed (verified both guides; 2026-10-16 15:12 ET).

## Review

### Standards

Fresh origin/main branch and dedicated worktree; both guide edits checked for matching wording and preserved CI/provider boundaries.

### Spec

Removes the named-PR approval requirement and the related merge stop in both requested guides.

### GoF

Documentation only; no production code or design-pattern change.
