# Clean MDM design reconciliation with Claude's handoff

Date: 2026-09-19. Reviewed source commit `b87fc05a`, after rebasing the clean
`codex/sec-gleif-company` worktree from merged core `e2807e52`. This is a
pre-implementation review. No runtime code, database schema or data changed.

## Pulled and reviewed

- PR #657: Clean MDM core, Company preparation and CI fixes, merged `e2807e52`.
  Its final GitHub checks passed, including 83 PostgreSQL integration tests.
- PR #658: accepted [Agent Open Query Surface ADR 0014](../../adr/0014-agent-open-query-surface.md)
  plus research and the standalone staging proposal, merged `cee23b11`.
- PR #659: [Claude's latest handoff](../../../.scratch/handover/2026-09-19-claude-to-codex-mdm-premerge-proposal.md),
  merged `b87fc05a`. Its sentence saying the handoff was not yet merged is now
  historical. The proposal itself remains a recommendation, not an accepted
  Clean MDM table design.
- [Company Q1–Q13](company-policy.md): current user answers govern scope,
  automatic linking/consolidation, exception handling and milestone completion.

The primary Claude checkout, its untracked deployment backup, Grok worktree,
old Codex worktrees and `.planning/active-workstream` were preserved.

## Correct the proposal's description of the current core

| Claim/gap | Verified current behavior | Design consequence |
| --- | --- | --- |
| Preview only handles duplicate keys | `clean/merge.py:395–400` runs the same SQL capability and rolls the complete transaction back for a new preview too | Keep full preview; persisted candidate assessment is an additional capability |
| No durable asynchronous review home | `merge.py:290–352` creates review projections; migration 023 stores them and immutable batch effects retain history | Extend/cross-reference current evidence and review records, rather than rebuilding a competing review authority |
| Identity replay equals matching | `identity.replay()` consumes accepted decisions; `store.py:155–156` and `merge.py:183–184` reject automatic rules | Candidate generation, fuzzy scoring and qualified automatic decision execution still need implementation |
| All identity corrections quarantine a whole Company | Current conflicting projection clears fields/profiles at `merge.py:279–284`; source binding cannot simply be moved in `identity.py` | Implement the newly accepted link-level suspension/replay contract; do not silently reassign a source or discard trusted SEC fields |
| Deferred records always block | Migration 027 requires blocking review per observing batch and prevents premature closure | Introduce an audited Company match-disposition contract via a new migration; do not weaken raw evidence-integrity checks or edit installed migrations |

A proposed new bind/merge that violates a hard identity veto still rolls back
before a durable review of that proposed action is retained. The useful new
capability is a queryable **pre-acceptance candidate assessment**, not a claim
that existing accepted/unbound evidence has no durable history.

## Adapt the persisted staging proposal

Recommend durable candidate assessments for proposed source bindings and
published-ID consolidations. Keep the name/table shape an implementation
choice. An assessment records subject and candidate IDs, full relevant component
membership, pinned source/evidence digests and checkpoint/epoch, rule/algorithm
versions and qualification references, scores, hard vetoes, proposed identity
and field/relationship differences, and its outcome/transition history.
Applied assessments link to the final decision, batch and publication lineage.

Constraints follow existing accepted boundaries:

1. Store assessments beside the transactional journal in `mdm_v2`, with
   immutable assessment/event history and separately rebuildable current status.
2. Persist them in a separate bounded transaction or evidence-only phase so they
   are visible across sessions. Writing a row immediately before master commit
   in the same transaction does not provide asynchronous inspection.
3. Assessment persistence is advisory: it creates no Company master, alias,
   source binding or selected field. `MergeStage.apply()` remains the only
   master-state transaction and reuses shared decision/field logic.
4. Qualified candidates progress automatically. Do not introduce a universal
   human approval step or hold a database lock while waiting for review.
5. Final application revalidates source evidence, policy/qualification,
   affected identity state and whole-component identifier/kind vetoes under
   the transaction lock. Stale proposals are superseded and recomputed;
   cached winners cannot be copied blindly into the master.
6. Staged/deferred work coexists with subsequent changes. Fence work by its
   relevant evidence and identity dependencies; unrelated Company progress
   must not wait on a staged candidate.
7. Rejection, supersession or operational expiry never deletes retained source,
   assessment/decision history or Match Exclusion. Hot status can be compacted
   separately; no new destructive retention policy is approved.
8. An assessment is neither a master commit nor a verified consumer receipt.
   Audited deferrals can count under Company Q12 only with its separate source,
   qualification, recovery and publication evidence.

Q13 resolution after this review: the user accepted assessment coverage for
**every** binding/consolidation proposal, including automatic decisions. Ordinary
field-only updates retain the existing evidence path. This resolves the last
coverage choice identified in the handoff review.
See [design gate 08](../../../.scratch/clean-mdm/issues/08-confirm-company-candidate-assessment.md).

## Reconcile other newly landed decisions

ADR 0014 locks a separate Agent Query Surface: MCP, raw SQL over PostgreSQL and
Snowflake, raw JSON, shared service authentication, a dedicated database-enforced
read-only role, and separate resource limits/pools. It declines attached
freshness/point-in-time result metadata for that surface. It does not remove
Clean MDM's stored provenance, journals, generation identity or required
publication receipts, and does not mandate changing Clean MDM's versioned API.

The ADR's “v1/v2 stay” refers to the Snowflake Decision Contract and Mongo
Decision Projection. Those are not the legacy/v2 MDM API versions. Preserve
those distinct names and requirements. No MCP implementation is added to this
Company workstream; future catalog/grants must describe the actual clean schema
and deny master-write capabilities, including security-definer functions.

Claude's DDL inventory describes the legacy `public` tables and is a dated
input, not a complete Clean MDM catalog. It must not be used to conclude that
`mdm_v2` is absent. The persistent local clean schema is distinct from the
legacy source/population counts; no schema deployment is inferred from a
merged migration file. A read-only check during this review found PostgreSQL
16.15, 27 `public` tables and 13 `mdm_v2` tables in local `mdm`, zero clean
batches, and migration 027’s deferred table not installed. These are local
observations, not hosted deployment evidence.

## Reconciled implementation order after design gate 08

1. Extend shared assessment, qualification, match-disposition and correction
   contracts while retaining transactional master/journal/outbox ownership.
2. Pin the tracked SEC Company manifest and approved SEC/GLEIF/OpenCorporates
   source publications; implement bounded capture/normalization and inventory
   validation. Unsupported kinds remain evidence, not coerced Companies.
3. Implement and qualify candidate generation/fuzzy source binding separately
   from authoritative existing-ID consolidation; apply field and parent policy.
4. Prove delta/gap recovery, retirement/suspension, stale-candidate fencing,
   reversal, duplicate/reordered delivery, exact accounting and local outputs.
5. Demonstrate qualified multisource results and audited outcomes across the
   frozen Company scope before advancing other entity integrations.

This review does not activate matching rules, approve an unverified source
snapshot, complete the Company milestone, or authorize hosted cutover.
