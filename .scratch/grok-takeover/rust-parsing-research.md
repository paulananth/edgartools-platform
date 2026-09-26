# Grok takeover: rust-parsing-research

Scope: preserve the authorized Grok work, verify it, and check it in on `codex/rust-parsing-research`. No deployment, matching-rule activation, database cleanup, or merge is included.

Recovery: original Grok worktrees are untouched. Heads, tracked patch and non-build untracked files are backed up at `~/.local/share/edgartools/branch-recovery/grok-takeover-20260926T171709Z/` with SHA-256 file manifest and Git bundle. Rust `target/` artifacts remain in the original worktree and are excluded from check-in.

- [x] Capture the source branch and unfinished files — bundle, patch and file manifest verified (2026-09-26 13:18 ET).
- [x] Transfer into a dedicated Codex branch/worktree based on `origin/main` `082d9461` — branch and status verified (2026-09-26 13:18 ET).
- [x] Review and document limits — research-only snapshot pinned to `b4faa6ac`; clarified independent HTML libraries; no refactoring or code changes warranted (2026-09-26 13:24 ET).
- [x] Verify the note — read all 457 lines, spot-check official quick-xml, serde_json, html5ever and lxml documentation; retain historical references and distinguish measurements from inference (2026-09-26 13:24 ET).
- [x] Review intended content — two Markdown files only; `git diff --check` passes, no secrets/build artifacts (2026-09-26 13:24 ET).
- [x] Commit and push — check-in `90d4bdb3` equals the remote hash and worktree is clean; this checklist update follows that verification (2026-09-26 13:25 ET).

## Review

No GoF refactor is warranted: this is a dated research note, not an implementation. The related parser histories and actual adapters remain intact. Code line references and package versions belong to the captured source revision; no Rust production adoption is approved.


## Verification

Primary-source spot checks on 2026-09-26: [quick-xml 0.37.5](https://docs.rs/quick-xml/0.37.5/quick_xml/), [serde_json](https://docs.rs/serde_json/latest/serde_json/), [html5ever](https://docs.rs/html5ever/latest/html5ever/) and [lxml.html](https://lxml.de/lxmlhtml.html). No benchmark was performed for this note. The separate heavy-parser branch contains the 13F experiment and its limits.
