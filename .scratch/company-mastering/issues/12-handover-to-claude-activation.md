# Ticket 12 handoff to Claude: Account hold-back activation (2026-09-25)

The operator asked Codex to finish the Account hold-back, then give the work
to Claude with this note. Codex's branch is
`codex/company-mastering-12-account-hold-back`; its draft PR is
[#712](https://github.com/paulananth/edgartools-platform/pull/712), which
supersedes Claude's still-open draft #710. The Codex worktree is
`/Users/aneenaananth/projects/edgartools-platform-worktrees/codex-cm-12-account`.
Do not commit to the Codex branch from Claude. Fetch it, create a new
`claude/<topic>` branch in a separate worktree, and check live `main` and PR
state before continuing.

## Exact approval and active rule

The operator selected **Approve this fingerprint** for the frozen inactive
policy digest
`31fdbef91859cd8f7423a827ae29156c190b013cff14cde184f3585a2c56f63f`.
Codex processed that reply at `2026-09-25T17:09:33Z` (13:09:33 ET), recorded
`approved_by: operator`, and activated the Account hold-back rule
`sec-company-candidate` version `2026-09-25.13` in
`edgar_warehouse/mdm/clean/company_source.py`. The resulting **active** policy
digest is
`35250dad7c22fe9404abda7af8b6be91fb5cfba43859aa531fcc18e2e0111321`.
Both the approved proposal and active digests are pinned in tests. The active
digest differs because the approval time and activation entry are part of the
policy body. Before any shared registration or merge, show the operator this
exact active digest for final review; the handover requires their word to
merge. No shared database was migrated, registered, or loaded by this work.

## What was proved

The frozen SEC bronze cohort contains 76,230 filers. The rule labels 6,414 as
Company (5,278 at step 8 and 1,136 at step 10); 91.58% wait in the Stage.
The frozen labeled sample has 600/600 Company calls, each Company step 300/300
with a 0.9911 one-sided 95% lower bound, and 0/328 adversarial violations.
The CI test re-hashes the files, re-scores the labels, and checks the current
rule still fires the recorded steps. The labels use bronze evidence and a
named list of 16 Funds; they are not independent registry adjudications of
all 928 sampled and adversarial rows. The retained ticker catalog is dated
2026-09-02. Deferred publication rereads after Probable Kind changes still
collide; the accepted 2026-09-23 limitation remains.

The standard policy now classifies Apple and Microsoft at step 8, Shell and
ASML at step 10, and defers the Tim Cook and Satya Nadella controls. The real
four-company PostgreSQL test uses the approved standard policy and passes.
Classification alone does not bind SEC CIKs to GLEIF LEIs or publish one
master Company; ticket 08 remains the critical next matching gate.

## Verification and review

- Focused activation/source tests: 87 passed.
- PostgreSQL 16 four-company tests: 5 passed.
- Full MDM and architecture tests after activation: 1,573 passed.
- Full PostgreSQL 16 Clean MDM suite after activation: 134 passed without
  skips in 8m05s (2026-09-25 13:21 ET).
- Ruff: passed. PR #712 CI after activation: check the latest head on the PR;
  it runs after this note and the activation commit are pushed.
- Standards/Spec/GoF review before activation found stale documentation and
  checklist entries and missing CI re-scoring; all were repaired. No GoF
  refactor was justified. The activation edit only supplies approval metadata
  and the already-reviewed automatic rule entry.

## Claude's next steps

1. Recheck this note against the final PR #712 head and green checks. Keep the
   active digest stable; if any policy body changes, compute and review its
   new digest before registering anything.
2. Ask the operator to review the exact active digest above and to authorize
   merging PR #712. The frozen-proposal approval alone did not authorize a
   merge. Do not merge draft #710.
3. Resume the wider Company milestone from
   `.scratch/company-mastering/remaining-work.md` and
   `docs/specs/clean-mdm/company-completion.md`. The SEC-to-GLEIF matching
   rule (ticket 08), dated Company table (09), latest-only Stage (10), whole
   proving run (05), and consumer/recovery acceptance are still open. Verify
   ownership of Claude's ticket-08 worktree before editing it.
