# Set the Clean MDM identity, merge, and recovery policy

Type: grilling
Status: claimed
Owner: Codex
Blocked by: 02

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

## Decision frontier after vendor research

The [vendor comparison](../../../docs/research/clean-mdm-vendor-merge-rules-2026-09-17.md)
supersedes the earlier blanket exact-only, numeric-threshold and smallest-ID
recommendations. The earlier proposal remains in git history; it was never
accepted. The following recommendations also remain unaccepted.

### Q1 — Automatic Source Record Binding

A new GLEIF record has a similar name, registered address and jurisdiction to
one Company, but no shared identifier. Can a tested rule bind it automatically,
or must every such case go to review?

Recommendation: allow exact and scored rules after entity-specific validation.
Do not choose numeric cutoffs before measuring false matches and missed
candidates. Incompatible kinds, authoritative-ID conflicts and multiple
eligible identities block automatic binding regardless of score.

### Q2 — Consolidation of established identities

Two already published Company Identities appear to be duplicates. May the
Merge Stage combine them automatically, or must a steward approve?

Recommendation: require steward approval in the first release. New evidence
may support an identity without authorizing a change to two published IDs.

### Q3 — Published-ID stability

Should adding a source ever change a Company's published ID? Must a rebuild
restore that same ID?

Recommendation: keep the published ID stable. An approved consolidation names
an existing survivor and retains aliases. Exact-ID replay restores the saved
identity registry and decisions as inputs. This replaces the earlier rule
that recomputed the smallest source-seed ID from the current evidence set.

### Q4 — Field authority and coherent groups

A newer lower-ranked source disagrees with an older approved authority.
Which wins, and may an address combine street/city/postcode from different
sources?

Recommendation: highest eligible field authority wins; explicit validity,
quality and freshness checks can make a value ineligible. Use source recency
within the authority order. Select a complete address together and retain all
conflicting claims. Apply deterministic ties at the pinned as-of time.

### Q5 — Blank, clear, and withdrawal

A source sends a blank where the master has a value. Does that erase the
value? What if the source explicitly withdraws its prior claim?

Recommendation: blank/unknown does not erase. An authorized clear can suppress
the field. Withdrawal retracts only that source's claim and allows another
eligible source to supply the value. Scope absence requires completeness proof.

### Q6 — Steward override lifetime

A steward corrects a field. The next source update disagrees. Does the update
replace the correction, or does the correction stay until expiry or review?

Recommendation: retain the correction until its declared expiry or explicit
revocation; contradictory updates create review. Exact durations and
field-specific exceptions follow this decision.

### Q7 — Reversal and Match Exclusion

A merge is reversed, but the same matching rule still calls the records a
match. Should the next run merge them again? Where do later corrections go?

Recommendation: retain a scoped Match Exclusion until an evidence-bound
decision revokes it. Recompute fields and relationships from retained source
bindings, keep later valid corrections, and review corrections whose owner is
unclear. Reversal completes only after downstream changes are verified.

## Remaining dependent decisions

Once this round is answered, settle numeric calibration/release criteria,
the survivor-selection rule for approved consolidations, override schedules,
and detailed reversal dependency handling. Additional domain representations
from the original gate (including Market/Venue and non-company Fund Structure)
also remain unresolved; vendor research is not their approval.

## Comments

2026-09-17 — Claimed by Codex in the dedicated worktree. Code and historical
decisions inspected. No answer inferred from the implementation request;
the plan explicitly requires these policies to be resolved through Wayfinder.

2026-09-17 — User requested vendor research and `grill-with-docs` before
answering. Research revised the recommendation set above. No approval was
inferred from that request; the previous “accept all seven” prompt is obsolete.

## Answer

Pending user decision. Do not generate implementation tickets or apply a
Clean MDM migration until this section records the actual exchange.
