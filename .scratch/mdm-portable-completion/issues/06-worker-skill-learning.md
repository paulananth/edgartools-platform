# Worker storage qualification lessons

Type: task
Status: claimed
Assignee: Codex
Parent: [Worker authority and publication recovery](06-connect-worker-authority-and-publication.md)

## Parts

- [x] Record populated index installation, stable function returns and unchanged catalog approval in the owning skill — 2026-10-25 20:44 ET; reviewed against the populated upgrade outcomes in #1171.
- [x] Record immutable delivery origin, durable execution metadata, complete publication accounting and separate verifier privilege proof — 2026-10-25 20:44 ET; reviewed against four independent installed worker cases in #1171.
- [ ] Check source neutrality, links and the skill diff; publish a separate skill PR.
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
