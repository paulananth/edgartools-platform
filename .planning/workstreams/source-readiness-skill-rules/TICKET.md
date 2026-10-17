# Put confirmed readiness rules in the data-platform skill

Scope: codify the operator's confirmed source-readiness and acceptance decisions
in the agent-facing skill. Documentation only; enforcement remains implementation
work. Separate branch/PR from the acceptance requirements, per repository rules.

- [x] Inspect existing guidance and current overlap; guard passed for both changed files, preserving Claude's separate mapping-pin work (2026-10-17 07:55 ET).
- [x] Add operational criteria for local qualification, common configured execution, full-delivery/no-op proofs, frozen versions and invalidation/repair; compared with the operator's individual yes answers and final confirmation (2026-10-17 07:55 ET).
- [x] Validate Markdown/frontmatter and review Standards, Spec and GoF applicability. YAML parsed offline; expected skill name/description and section structure valid; whitespace and overlap checks passed. No runtime code or behavior test changed (2026-10-17 07:55 ET).
- [x] Commit/push and open separate skill PR #1040; independent documentation sync required no edits. Acceptance requirements are in PR #1039; this branch changes agent instructions only (2026-10-17 07:58 ET).
- [x] Learning → skill: `skills/data-platform/SKILL.md`, Source readiness section, now carries the confirmed acceptance rules. It explicitly requires agents to report missing runtime enforcement as a gap; documentation is not proof that enforcement exists (2026-10-17 07:55 ET).

## Standards

Separate skill branch/worktree; no unrelated code or Claude-owned edits staged.
Public requirements and invented examples only. Package frontmatter unchanged.

## Spec

Every confirmed decision is represented, including the distinction between
ordinary version supersession and explicit invalidation. Installed agents can
read these instructions without relying on repository-only design links.

## GoF

No runtime code or interface change. Pattern refactoring is inapplicable to this
documentation-only change; implementation consult/review remains a separate step.
