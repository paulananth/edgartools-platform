# Integer width policy

Status: claimed. Operator instruction, 2026-10-16: "also never use int always use long or bigint".

## Checklist

- [x] Record the integer-width rule in AGENTS.md and replace CLAUDE.md's narrower, conflicting convention with a pointer — 2026-10-16 14:48 ET; all integer fields/counters covered, old bounded-year/quarter exception removed, Python arbitrary precision and overflow preservation explicit.
- [x] Verify the documentation diff, anchors, and shared-path overlap under Standards, Spec and GoF — 2026-10-16 14:48 ET; focused assertions, anchor and whitespace checks pass; overlap guard clean for three documentation files; review below.
- [x] Commit and push the dedicated branch and open its review PR — 2026-10-16 14:51 ET; 0b9bafc2 pushed after guard checks, PR [#1019](https://github.com/paulananth/edgartools-platform/pull/1019) open with three documentation files.
- [ ] Land PR #1019 only with green CI and the operator naming it for merge.
- [x] Learning → skill — 2026-10-16 14:48 ET; AGENTS.md Integer widths is the canonical standing rule, CLAUDE.md points there. No private memory changed.

## Scope

This is guidance for integer columns, native fields and counters. Python's built-in integer already has arbitrary precision. This ticket changes no runtime types, applied migrations, data values or stores. Any schema migration remains separately scoped and verified.

## Review

### Standards

Fresh dedicated branch/worktree; three documentation files; shared-path guard clean. No runtime tests are required for this guidance-only diff. No provider values or requests.

### Spec

The operator's BIGINT/long requirement covers bounded integer fields as well as counters. Python arbitrary precision remains intact, and values outside the target width are preserved and flagged rather than coerced. Existing source files and applied migrations remain unchanged.

### GoF

The refactor-review method is available. This diff changes guidance only; there is no program interface or design pattern to refactor.
