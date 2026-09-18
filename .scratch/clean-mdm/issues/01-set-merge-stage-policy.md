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
accepted. On 2026-09-18 the user accepted Q1–Q12 across three rounds. Ask no more
than three questions per round, as explicitly requested by the user.

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

The survivor rule, numeric precision target and non-company Fund Structure
boundary are accepted. Actual score cutoffs still require measured calibration;
no validation result is implied. Branch, Government Entity and Market/Venue
representations remain unresolved.

## Completed clarification round

Q3 fact check against this checkout: `mdm_entity.entity_id` is already a UUID
primary key (`edgar_warehouse/mdm/migrations/001_initial_schema.sql:25`).
Normal updates reuse it, but allocation mixes random UUID4 and source-seeded
UUID5 paths. Steward merges tombstone the discarded ID and move source refs
(`edgar_warehouse/mdm/stewardship.py:130–174`); redirects are consumer-specific,
not a general alias contract. An empty-database rebuild cannot reproduce all
random IDs from source bytes. The accepted decision strengthens continuity through
merges, reversals and replay; it does not introduce the first internal ID.

- **Q3 — Internal identity ID:** retain an immutable internal ID independent of
  CIK/LEI and other source identifiers? Recommend yes: one ID per identity,
  shared by its roles; an approved consolidation retains losing IDs as aliases,
  and exact-ID replay restores the registry and accepted decisions. Existing
  survivor selection remains a dependent decision.
- **Q8 — Override expiry default:** when a steward gives no expiry, should the
  correction remain until explicitly revoked? Recommend yes; allow an explicit
  expiry, keep conflicting updates in review, and do not invent per-field
  expiration periods before a field contract requires them.
- **Q9 — Dependent merges during reversal:** if a later merge relied on the
  incorrect merge, may the system guess how to split it? Recommend no: require
  review of that affected dependency before activating the reversal; unrelated
  identities continue processing. Independently supported corrections remain.

## Completed survivor, accuracy and fund round

- **Q10 — Survivor selection:** recommend the earliest published identity as
  the default survivor, with UUID ordering only for equal publication times.
  A steward can select another existing ID with a recorded reason; all losing
  IDs remain aliases. Survivor selection does not determine field winners.
  Pin publication history and the steward decision for replay; never use source
  arrival order or a newly introduced source key to change a published ID.
- **Q11 — Automatic-binding release target:** propose at least 99.9% precision,
  demonstrated by a one-sided 95% lower confidence bound on representative,
  independently labeled held-out auto-binding decisions per enabled entity-kind
  and rule family. This is an accepted business risk target, not a vendor fact,
  a similarity cutoff or a guarantee. Also require zero hard-veto violations in
  adversarial fixtures, measure candidate recall and review volume, and keep
  unsupported/under-sampled rules review-only. Calibrate actual score cutoffs
  from the corpus and record them before implementation tickets; no universal
  similarity score is assumed.
- **Q12 — Non-company funds:** recommend a distinct Fund Structure identity
  with a Fund profile for supported non-company arrangements. Incorporated
  company funds retain Company identity plus Fund profile. Evidence determines
  the structural level; umbrella/subfund relationships remain explicit and
  securities representing shares remain separate. Unclear form or level stays
  evidence-only until adjudicated.

## Next round (maximum three questions)

- **Q13 — Branch:** recommend a distinct Branch identity linked to its head
  office, even where it is not a separate legal person. Neither a shared name
  nor a head-office identifier establishes branch identity. Retain evidence
  when the branch/head-office mapping is unresolved.
- **Q14 — Government Entity:** recommend a distinct kind for supported
  government bodies. Government ownership alone does not change a legally
  incorporated Company's kind; retain that ownership as a relationship.
  Ambiguous legal status stays in review. International Organization remains
  the previously accepted common-registry kind.
- **Q15 — Market/Venue:** recommend distinct venue identities linked to their
  operators, with operating/segment MIC relationships represented as dated
  venue hierarchy. Neither venue/operator links nor venue hierarchy imply
  corporate ownership. Retain identifier history and defer ambiguous mappings.

Actual rule calibration is a research prerequisite, not another request for
user-supplied score numbers. Additional consumer/source contracts follow the
accepted domain boundaries before publication is enabled.

## Comments

2026-09-17 — Claimed by Codex in the dedicated worktree. Code and historical
decisions inspected. No answer inferred from the implementation request;
the plan explicitly requires these policies to be resolved through Wayfinder.

2026-09-17 — User requested vendor research and `grill-with-docs` before
answering. Research revised the recommendation set above. No approval was
inferred from that request; the previous “accept all seven” prompt is obsolete.

## Answer

Partial acceptance on 2026-09-18. User: “q1 yes, q2 yes, Q3 do we have an internal
immutable id ?, q4 yes, q5 agreed, q6 agreed, q7 agreed ask three questions at a
time not more than that”.

In the next exchange the user said: “q3 yes, q8 agreed, q9 agreed”.
Q1–Q9 are now accepted: internal IDs persist with aliases and registry-based
replay; overrides without expiry remain until explicit revocation; dependent
merges require review before reversal activation while unrelated work continues.
The user then replied “accept recommendation” to Q10–Q12. These three
recommendations are accepted: earliest-published default survivor with recorded
steward exceptions and aliases, the 99.9% precision/95% confidence release target,
and distinct non-company Fund Structure identities with Fund profiles.
Actual calibrated scores and remaining domain contracts are unresolved. The
overall gate stays claimed; no implementation tickets or Clean MDM migrations
are created by this partial resolution.
