# Worker storage qualification lessons

Type: task
Status: in review
Assignee: Codex
Parent: [Worker authority and publication recovery](06-connect-worker-authority-and-publication.md)

## Parts

- [x] Record populated index installation, stable function returns and unchanged catalog approval in the owning skill — 2026-10-25 20:44 ET; reviewed against the populated upgrade outcomes in #1171.
- [x] Record immutable delivery origin, durable execution metadata, complete publication accounting and separate verifier privilege proof — 2026-10-25 20:44 ET; reviewed against four independent installed worker cases in #1171.
- [x] Check source neutrality, links and the skill diff; publish a separate skill PR — 2026-10-25 20:45 ET; eight affected checks pass and PR #1173 publishes the guidance separately. PR readiness and merge retain their CI gate.
- [x] Resolve the CI timeout by rebasing onto implementation #1171 — 2026-10-25 21:35 ET; MySQL storage and reference caller steps passed before migration recovery exceeded the cumulative 15-minute job limit. Rebase is conflict-free and inherits independent required MDM/RDM/Silver jobs; this PR still adds only two documentation files.
- [ ] Require final-head CI and finish PR readiness; implementation #1171 must land before this skill change.
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
PR #1173 is stacked on #1171 to inherit the existing workflow fix without a second
CI implementation. After #1171 merges, retarget this PR to main and rebase away
its squash-merged implementation ancestry before merging. Final-head CI remains
a separate gate.
