# Complete database skill publication and account for Codex branches

Status: in progress. The operator asked to complete
`codex/database-agnostic-data-skills-20261017` and explain why branches were
left without committed changes or PRs. This ticket closes the publication gap;
it does not claim unfinished native database integration is implemented.

## Checklist

- [x] Verify #1070 merge as `3b39db5a`, all six successful checks on tested head `f84cc19f` and the named branch's ticket-only residual commit — 2026-10-18 14:42 ET.
- [x] Audit all 13 existing Codex worktrees: all clean; four branches with merged PRs, six with unpublished records, three with no changes; remote/PR inventory checked live — 2026-10-18 14:42 ET.
- [x] Carry six operational records from existing Codex commits, including the duplicate closeout that supersedes the named branch's residual note, into this fresh closeout branch; only Markdown changes — 2026-10-18 14:42 ET.
- [x] Correct the original ticket's merge status and stale open-PR wording, preserving its original CI evidence and later skill/adapter implementation unchanged — 2026-10-18 14:42 ET.
- [x] Record every branch disposition below; historical database snapshots are dated and the Company integration/activation checklist remains incomplete — 2026-10-18 14:42 ET.
- [x] Add the PR handoff requirement under AGENTS.md, Commits/PRs: include operational records, keep unfinished closeout/validation in draft and use a fresh branch after merge; planned and actual overlap guards pass — 2026-10-18 14:42 ET.
- [x] Review Standards, Spec and GoF; validate all eight changed files are Markdown-only, ten local references resolve, no connection strings are present, and whitespace/overlap checks pass; original #1070 checks and current-main CI are green — 2026-10-18 14:44 ET.
- [ ] Commit, push and create a PR; verify checks with a bounded watcher that exits on every outcome.
- [x] Learning → skill: repository handoff belongs in AGENTS.md, Commits/PRs; a local or pushed operational-note commit alone is not a completed review handoff — 2026-10-18 14:42 ET.

## Scope

Retain original branches/worktrees and other runtimes' WIP. Do not rewrite a
merged branch, reintroduce old skill content, duplicate a completed runtime
change, or merge a PR without the applicable operator authorization. Existing
operational records retain their measured scope, dates and open checklists.

## What was actually missing

The original database-agnostic skill requirement was delivered in
[merged #1070](https://github.com/paulananth/edgartools-platform/pull/1070).
The four skill files need no replay over later main changes. A CI-status note
was committed after its PR merged, and a second fresh verification branch
held a more accurate version of that same note; neither received a closeout
PR. Other operational tasks stopped at a local or pushed commit. That is a
publication/handoff error, not uncommitted engine code. This PR publishes
the missing records together and makes the original ticket's outcome accurate.

## Branch audit, 2026-10-18 14:42 ET

All worktrees below were clean. `PR` means the branch's actual GitHub PR,
not an inference from Git ancestry: squash merges preserve a different main
commit and can leave an old branch looking ahead.

| Existing Codex branch suffix | Before this closeout | Disposition |
|---|---|---|
| `database-agnostic-data-skills-20261017` | #1070 merged; later `cc51b90b` ticket note outside review; remote branch removed | Original skill task complete. Its residual note is superseded by the more accurate verification note included here. Preserve original ref. |
| `database-skills-ci-verification-20261017` | Local-only `f1aac602`, no PR | Its corrected #1070 merge/CI record is included here. No duplicate skill implementation. |
| `three-database-test-instances-20261017` | Local-only `a01bf6a0`, no PR | Historical creation record included here; later database changes explicitly distinguished. |
| `initialize-company-person-test-servers-20261017` | Local-only `cbbd60f3`, no PR | Historical partial initialization record included here; native support/qualification remain open. |
| `native-pipeline-activation-three-databases-20261018` | Pushed `bdaa5b4f`, no PR | Preflight record included here; obsolete artifact-path dependency corrected after retained-input discovery. |
| `company-three-engine-readiness-20261018` | Pushed `dfbbdfe9`, no PR | Active Company-only remaining-work record included here. Existing engine/adapter repair remains open; Person deferred. |
| `verify-ci-identifier-fixture-20261018` | Pushed `b1def861`, no PR | Completed, dated CI verification record included here. The actual runtime/test fix was already merged by its owner. |
| `data-platform-completion-guide-20261018` | #1077 merged at `4f710059` | Already reviewed; preserve ref, replay nothing. |
| `deploy-company-person-three-databases-20261017` | #1073 merged at `059d1758` | Already reviewed; preserve ref, replay nothing. Storage qualification remains distinct from native activation. |
| `source-evidence-relationship-modules-20261017` | #1067 merged at `3270e45b` | Already reviewed; preserve ref, replay nothing. |
| `architecture-existing-suggestions-20261017` | No changes beyond its base; no PR | No reviewable diff. Preserve the empty worktree/ref. |
| `source-extract-evidence-design-20261017` | No changes beyond its base; no PR | No reviewable diff. Preserve the empty worktree/ref. |
| `fix-native-engine-adapter-20261018` | No changes beyond its base; no PR | No implementation was made before the CI interruption. Preserve the ref and carry the engineering scope in the Company task. |

This new `codex/database-skills-closeout-20261018` branch starts at
`cc399da5`, holds only the residual records/handoff correction, and is the
single review surface for those notes. Original branches, commits and private
operational receipts are retained for recovery. No force push or deletion.

## Standards

Fresh branch/worktree from current main. Planned shared-path and actual
overlap checks pass; no other runtime's files changed. Source commits belong
to Codex. No secrets, database addresses or source records are introduced.
Public evidence is counts, static container names and dated capability refusals.
All imported records are Markdown; code, rules, SQL, package contents and
CI configuration are identical to the base. Final publication remains in
draft until the checklist and final-head checks are complete.

## Spec

The named skill branch already completed its configuration/engineering
contract through #1070. This closeout publishes the residual record and the
related PR-less records, explains every existing Codex branch, and repairs the
handoff process. It does not turn on Company or claim native MySQL/SQL Server
pipeline integration. Those unchecked business-operation items are retained
in the Company task and remain constrained to the existing engine/adapter.

## GoF

`gof-refactor-reviewer` is available and its method is applied to the same
publication diff/history. This is a documentation-only correction of stale
status and an incomplete handoff. Retain the current engine/adapter design;
no pattern, new runtime layer or additional implementation is justified here.

## Validation

The closeout changes eight Markdown files, with ten local Markdown references
checked against this checkout. No engine, adapter, rules, SQL, package or
CI files change. Whitespace and planned/actual ownership guards pass. Existing
feature proof is #1070's six successful checks on `f84cc19f`; base main
`cc399da5` also has nine successful checks in
[run 39153684808](https://github.com/paulananth/edgartools-platform/actions/runs/39153684808).
The closeout's own CI result will be retained with its PR before readiness.
