# Coordination: Claude and Codex

status: active
updated: 2026-06-01

---

## Rule

Claude and Codex can work independently on this project, but each runtime must operate in an isolated workstream and avoid touching the other runtime's active files.

## Repository Policy (LOCKED)

**`edgartools` is a read-only reference repository.**
- Never commit to `edgartools` — not checkpoints, docs, planning files, or code.
- All development work, planning docs, session files, and checkpoints go in `edgartools-platform`.
- `edgartools` is used only to read library source, understand APIs, and reference examples.
- Agents may clone/read `edgartools` but must never stage or push changes to it.

## Operating Protocol

- Use separate git worktrees or branches when both runtimes are active.
- Use distinct GSD workstream directories under `.planning/workstreams/<name>/`.
- Check `git status --short` before edits and treat existing uncommitted changes as owned by another runtime unless proven otherwise.
- Check `.planning/active-workstream` before planning or executing GSD work.
- Do not edit another runtime's active workstream artifacts, generated deployment outputs, or in-progress source files without explicit user approval.
- If both runtimes need the same file, pause and get a user ownership decision before editing.
- Commit or stage only files from the current runtime's assigned workstream and code scope.

## Current Note

The repository currently has an active GSD workstream named `neo4j-snowflake`.
Treat unfinished `mdm-neo4j-dashboard`, `neo4j-pipe`, and `fix-pipelines` artifacts as
protected unless the user explicitly reassigns or hands them off.
