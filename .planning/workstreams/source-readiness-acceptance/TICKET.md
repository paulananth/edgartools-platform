# Source readiness: acceptance and invalidated inputs

Status: interview and documentation handoff complete; PR #1039 open.
Requirements only; runtime implementation, activation and loading remain separate.
This extends the design merged in PR #1036 without editing Claude's ticket 103.

- [x] Inspect current main and isolate documentation in a new worktree/branch. Main is `1db543026`; primary checkout's unrelated changes preserved. Claude continues its separate mapping-pin implementation (2026-10-17 07:52 ET).
- [x] Record Q1: verified retained captures can qualify local processing through normal Rules validation, provenance and completeness evidence, independently of AWS capture qualification. User answered yes; provider requests remain separate (2026-10-17 07:52 ET).
- [x] Record Q2: readiness requires an entire available retained-delivery run with every record accounted for, followed by an unchanged repeat selecting zero files and no new mastering work. User answered yes; waiting relationships are explicitly counted (2026-10-17 07:52 ET).
- [x] Record Q3: explicit invalidation stops affected work, preserves verified progress and requires repair with valid inputs; no silent repinning. Ordinary version supersession leaves original run pins intact. User answered yes (2026-10-17 07:52 ET).
- [x] Record Q4: results already produced from invalidated inputs cannot feed dependent work until repaired. Retain provenance/history, schedule normal-path correction and allow unrelated work to continue. User answered yes (2026-10-17 07:52 ET).
- [x] Check the recorded requirements and documentation links; user answered yes to the final shared-understanding question. Local Markdown links verified and requirements compared with all four answers (2026-10-17 07:54 ET).
- [x] Commit/push the confirmed documentation and open PR #1039. Independent documentation sync required no edits. Handoff launched as Claude session `9096f95d`, verified working, in a separate planning worktree restricted to its own implementation-plan artifacts. Existing mapping-pin session/PR #1037 remains separate and unchanged (2026-10-17 07:58 ET).
- [x] Learning → skill: Source readiness section added to `skills/data-platform/SKILL.md` on its own branch, PR #1040. Offline frontmatter/structure, whitespace and overlap checks passed; the skill explicitly distinguishes acceptance requirements from missing runtime enforcement (2026-10-17 07:58 ET).

## Decision tree

1. Can local captures qualify before AWS capture production? Yes, with genuine
   qualifying evidence and normal lifecycle checks.
2. What earns readiness? Full retained-delivery proof plus unchanged-repeat proof;
   code/fixture tests alone are implementation evidence.
3. What overrides frozen run versions? Explicit invalidation stops affected work;
   an ordinary newer version does not.
4. What happens to already-produced dependent results? They are unavailable as
   inputs until repaired; history remains and unrelated work continues.
5. Final shared-understanding check: confirmed. No remaining unasked business
   question identified in this interview; implementation details remain engineering
   work subject to existing rules and meaningful behavior tests.

Requirements: [source readiness acceptance](../../../docs/specs/source-readiness-acceptance.md).

## Standards

Dedicated worktree and scoped public documentation; private source evidence
retains its existing boundaries. Both branches passed overlap checks, and no
other runtime's branch, files or shared database was changed.

## Spec

All four choices and final shared understanding are recorded. The confirmed
contract and the matching skill instructions have separate reviewable PRs.
The handoff has the exact artifacts and a separate planning-only edit surface.

## GoF

Documentation and operational requirements only; no runtime pattern or interface
change. Implementation still needs its own consult, behavior proof and review.
