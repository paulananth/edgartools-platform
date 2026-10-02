# Use GitHub CLI for repository operations

Owner: Codex. Branch: `codex/fresh-work-20261002`. Status: in progress.
Worktree: `edgartools-platform-codex-fresh-work-20261002`.
Base: current main `b6474bf24c8d2bd275c921220977d68ef9959c06`.

## Checklist

- [x] Verify the prior cleanup branch is rebased and synced; create this fresh branch/worktree from current main. — no-op rebase verified, cleanup refs match 7fa6dc81, dedicated fresh worktree initially at main b6474bf2; 2026-10-02 15:49 ET.
- [x] Diagnose the missing `gh` executable, restore it and verify existing GitHub authentication. — gh absent from PATH and Homebrew locations; checksum-verified official 2.102.0 binary installed in ~/.local/bin; gh auth status confirms paulananth; 2026-10-02 15:49 ET.
- [x] Add the GitHub CLI rule to AGENTS.md and check its scope and wording. — two scoped Tooling Rules bullets reviewed using writing-for-agents; exact prerequisites and fallback condition documented; 2026-10-02 15:49 ET.
- [x] Verify protected shared files and stashes remain unchanged; check the final diff. — shared HEAD/status and two SHA-256 hashes match the pre-sync snapshot; stash refs match; git diff --check passes; 2026-10-02 15:49 ET.
- [ ] Commit/push and publish the instruction change through `gh`.

## Scope

The operator requested a fresh branch/worktree, then required `gh` usage to be
documented in AGENTS.md. The cleanup PR #797 remains separate and unmerged.
The inherited `fix-pipelines` marker is shared history; this task owns only
AGENTS.md and this checklist in its dedicated worktree.

The gh failure was a missing executable, not a sandbox restriction. The restored
binary uses the existing keyring login; no reauthentication was needed.
