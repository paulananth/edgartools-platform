# Complete the case-by-case test review

Status: in progress. Branch starts at `5f264261c`; PR #1197 already merged the first 127 proven duplicate cases. This follow-up reconciles the remaining reviewed draft with current main. The operator authorized Luna subagents with low reasoning and retirement only for demonstrated redundancy.

- [x] Preserve the unfinished draft and create a fresh worktree — 2026-10-28 18:17 ET: binary patch and untracked files backed up privately with checksums; dedicated Codex branch from origin/main.
- [ ] Reconcile current-main changes with the completed Python and Rust source review; retain new or changed obligations unless equivalence is demonstrated.
- [x] Apply the non-overlapping reviewed removals — 2026-10-28 18:25 ET: 63 removed IDs mapped in completion-retirement.json; all retained-test targets resolve, no added cases; the worker helper body is AST-identical.
- [ ] ~~Remove two activation duplicates~~ deferred until the active Claude t138 edits land: overlap guard identifies `tests/mdm/test_clean_activation.py`; this branch restores that file to HEAD and retains the draft privately.
- [ ] Verify retained behavior, collection and negative proofs with bounded affected testmon runs.
- [ ] Review Standards, Spec and GoF, publish a PR and verify final-head CI.
- [ ] Learning → skill: record the case-level review method and replace the obsolete plan-cache test pointer in a separate skill PR.

The separate skill draft passes 80 generic lint checks. Its publication is
pending an ownership decision: the overlap guard names Claude t132 and t138
worktrees for `skills/mdm-engineering/SKILL.md`.

Counts of collected cases measure maintenance surface. They do not prove runtime improvement. Detailed source-level audit evidence and diagnostics stay private; public artifacts contain counts and outcomes only.
