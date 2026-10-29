# Worker storage qualification lessons

Type: task
Status: resolved
Assignee: Codex
Parent: [Worker authority and publication recovery](06-connect-worker-authority-and-publication.md)

## Current closeout — 2026-10-28 20:12 ET

PRs #1173 are merged; 13 final-head checks pass. Current qualification is 160 installed cases per engine, two configured kinds and all 18 families at #1210. [Closeout evidence](../assets/completion-evidence.json) records the verified heads and limits. Historical checkpoints below retain their original dates.

## Parts

- [x] Record populated index installation, stable function returns and unchanged catalog approval in the owning skill — 2026-10-25 20:44 ET; reviewed against the populated upgrade outcomes in #1171.
- [x] Record immutable delivery origin, durable execution metadata, complete publication accounting and separate verifier privilege proof — 2026-10-25 20:44 ET; reviewed against four independent installed worker cases in #1171.
- [x] Check source neutrality, links and the skill diff; publish a separate skill PR — 2026-10-25 20:45 ET; eight affected checks pass and PR #1173 publishes the guidance separately. PR readiness and merge retain their CI gate.
- [x] Resolve the CI timeout by rebasing onto implementation #1171 — 2026-10-25 21:35 ET; MySQL storage and reference caller steps passed before migration recovery exceeded the cumulative 15-minute job limit. Rebase is conflict-free and inherits independent required MDM/RDM/Silver jobs; this PR still adds only two documentation files.
- [x] Rebase onto current main after implementation #1171 merged — 2026-10-25 21:46 ET; clean rebase onto 4fb26ae4 retains only the two documentation files.
- [x] Require final-head CI before merge — 2026-10-28 20:12 ET: #1173 merged; all 13 reported checks pass.
- [x] Learning → skill: `mdm-engineering/references/storage-adapters.md`, owner installation and execution/delivery recovery — 2026-10-25 20:44 ET; eight affected source-neutrality checks pass, and whitespace/link review passes.

## Evidence

Implementation PR #1171 retains the code and invented-fixture outcomes. Its
independent five-wheel worker checks qualify two kinds and two sources on each
engine with separate SELECT-only verifier logins. Populated upgrade checks found
that existing tables needed explicit installation of the added observer index.
Delivery interruption/retry preserves one original downstream event. Final CI
and completion of the implementation remain separate gates.

## Review

### Standards

Separate skill branch/worktree, source-neutral guidance, no new commands or
runtime readiness claim; eight affected neutrality tests and whitespace pass.

### Spec

Records the demonstrated migration and delivery lessons; installation,
qualification, activation and final CI remain distinct gates.

### GoF

Documentation only. Preserve the existing store, worker and publication seams;
the guidance introduces no pattern hierarchy or new execution owner.

## CI repair

The original MySQL job annotation reports a 15-minute timeout, not a failed assertion.
The initial stack inherited #1171’s workflow fix without a second CI implementation.
After #1171 merged, this branch was rebased onto main 4fb26ae4, removing the
squash-merged implementation ancestry. The PR now targets main; final-head CI
remains a separate gate.
