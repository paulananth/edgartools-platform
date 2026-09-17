# Set the Clean MDM identity, merge, and recovery policy

Type: grilling
Status: claimed
Owner: Codex
Blocked by: none

## Question

Which concrete identity representations, matching thresholds, field semantics,
surviving-ID rule, relationship reassignment, and merge-reversal contract will
govern the new isolated MDM? This is the explicit pre-implementation gate in
the user's plan, not an implementation ticket.

## Review assets

- [Domain and relationship model](../../../docs/specs/clean-mdm/domain-model.md)
- [Pipeline and source inventory](../../../docs/specs/clean-mdm/pipeline-inventory.md)
- [Source evidence contract](../../../docs/specs/clean-mdm/source-evidence.md)
- [Merge Stage proposal](../../../docs/specs/clean-mdm/merge-stage.md)
- [Journal and recovery proposal](../../../docs/specs/clean-mdm/recovery.md)
- [Acceptance and qualification plan](../../../docs/specs/clean-mdm/acceptance.md)

## Decision frontier

Each recommendation is proposed, not accepted. The entire frontier is shown
together so the user can accept it together or revise individual choices.

| Gate | Recommendation | Consequence / alternative |
| --- | --- | --- |
| Identity representations | Branch and Government Entity are distinct kinds; International Organization is a typed common-registry identity without a dedicated domain table; Market/Venue is distinct from its operator; non-company Fund is a `fund_structure` identity with an explicit legal/structural form | Avoids forcing legal or contractual structures into Company. A broader party supertype would require a separate migration decision. |
| Scoring and conflicts | Exact, unique, authoritative identity match scores 1.00 and is the only automatic consolidation in v1; fuzzy review begins at 0.85 for Company and 0.80 for Person; all other kinds use exact-only plus explicit review | Lower fuzzy automatic thresholds need a labeled validation corpus. Kind mismatch and authoritative-ID disagreement veto every score. Multiple candidates never use a tie-break to authorize identity. |
| Nulls, corrections, retirement | Distinguish absent field, unknown, explicit value, authorized clear, and source retraction; corrections supersede one source record; absence retires assertions only after proven complete scope | Prevents missing data or a partial snapshot from erasing a master. Clear blocks lower-ranked fallback; retraction permits fallback. |
| Field priorities and ties | Versioned field/role authority, then source effective time, source-native correction order, then stable source/record/assertion keys; retain losing evidence | Deterministic selection only among eligible non-identity fields. Ingest time and database row order have no voting power. |
| Surviving identity | Deterministic identity seeds from immutable source-record anchors; lexicographically smallest seed UUID survives an accepted same-kind merge; every other ID remains an alias | Produces order-independent final IDs for the same accepted evidence/decisions, but the canonical ID can change when new evidence joins a component. Existing aliases remain resolvable. |
| Relationship reassignment | Recompute current endpoints from immutable asserted endpoints and accepted identity bindings; preserve original evidence, dates, and derivation lineage | No destructive rewrite of reported history. Invalid endpoints, self-links, temporal cycles, or conflicting single-parent edges block affected publication. |
| Reversal | Revoke a merge decision through a new journal event, replay its affected closure under pinned policies, restore prior identity partitions, and publish compensating changes | More work than restoring a snapshot, but retains valid later corrections. Ambiguous post-merge evidence returns to review; dependent merges require review before new publication. |

## Comments

2026-09-17 — Claimed by Codex in the dedicated worktree. Code and historical
decisions inspected. No answer inferred from the implementation request;
the plan explicitly requires these policies to be resolved through Wayfinder.

## Answer

Pending user decision. Do not generate implementation tickets or apply a
Clean MDM migration until this section records the actual exchange.
