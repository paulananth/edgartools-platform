# Complete the case-by-case test review

Status: in progress. Branch starts at `5f264261c`; PR #1197 already merged the first 127 proven duplicate cases. This follow-up reconciles the remaining reviewed draft with current main. The operator authorized Luna subagents with low reasoning and retirement only for demonstrated redundancy.

- [x] Preserve the unfinished draft and create a fresh worktree — 2026-10-28 18:17 ET: binary patch and untracked files backed up privately with checksums; dedicated Codex branch from origin/main.
- [x] Reconcile current-main changes with the completed Python and Rust source review — 2026-10-28 18:28 ET: all 4,198 active baseline IDs covered by the prior ledger plus 48 explicitly reviewed new IDs; 16 changed Python bodies and eight added Rust tests reviewed; all new obligations retained. This is source review, not an execution claim.
- [x] Apply the non-overlapping reviewed removals — 2026-10-28 18:25 ET: 63 removed IDs mapped in completion-retirement.json; all retained-test targets resolve, no added cases; the worker helper body is AST-identical.
- [ ] ~~Remove two activation duplicates~~ deferred until the active Claude t138 edits land: overlap guard identifies `tests/mdm/test_clean_activation.py`; this branch restores that file to HEAD and retains the draft privately.
- [x] Verify retained behavior, collection and negative proofs — 2026-10-28 18:30 ET: local cohorts 142, 235 and 179 passed; PostgreSQL 11 passed (204.31 seconds), MySQL 11 passed (219.60 seconds); eight collections error-free; 23 injected faults rejected. Every local invocation stayed below five minutes.
- [x] Review Standards, Spec and GoF and publish a PR — 2026-10-28 18:33 ET: root review in COMPLETION-EVIDENCE.md and independent Luna final review found no findings; all 55 new pytest targets, four CI targets and 127 prior targets resolve; four obsolete obligations are recorded separately. PR #1210 is draft pending CI.
- [ ] Verify final-head CI, installed case accounting and cleanup; mark PR #1210 ready only after every check passes.
- [x] Keep reference-data parameters out of public audit metadata — 2026-10-28 18:51 ET: seven case fingerprints map exactly to retired collected IDs in the private ledger; all 63 case decisions and retained targets are preserved.
- [ ] Learning → skill: record the case-level review method and replace the obsolete plan-cache test pointer in a separate skill PR.

The separate skill draft passes 80 generic lint checks. Its publication is
pending an ownership decision: the overlap guard names Claude t132 and t138
worktrees for `skills/mdm-engineering/SKILL.md`.

Counts of collected cases measure maintenance surface. They do not prove runtime improvement. Detailed source-level audit evidence and diagnostics stay private; public artifacts contain counts and outcomes only.
