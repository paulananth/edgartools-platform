# Shared Merge Stage

Status: proposed policy v1; requires the
[Wayfinder decision](../../../.scratch/clean-mdm/issues/01-set-merge-stage-policy.md).
Numeric thresholds below are conservative recommendations, not measured model
accuracy or permission to change the running matcher.

## Inputs and outputs

A bounded work request names the root `run_id`, consumer/version, pinned
publication set, record-key range, expected predecessor checkpoint, and
immutable policy digest. Its durable business key excludes attempt and run
IDs so a retry or a new run cannot duplicate an already committed effect.

One Merge Stage transaction validates evidence and policy, resolves identity,
selects role and identity fields, validates/reprojects relationships, writes
commit evidence, advances the fenced checkpoint, and enqueues every required
consumer's publication intent. Return the durable batch result, including
unresolved dispositions. No adapter, API override, bulk loader, seed, repair,
or reconciliation path writes master state around this entry point.

## Identity matching policy proposal

Score candidates only within the same accepted identity kind and approved
identifier scope. Check the whole proposed merged component for conflicts,
not just the incoming record against one preferred candidate. A third record
bridging two conflicting identifiers cannot transitively bypass the veto.

| Kind | Automatic | Review candidate generation |
| --- | --- | --- |
| Company | 1.00 for exact unique authoritative CIK/LEI or jurisdictional registration identity, with compatible kind and no conflicting authoritative identifier | Normalized-name Jaro-Winkler at least 0.85; include jurisdiction/address comparisons as evidence, never as automatic boosts |
| Person | 1.00 for exact unique authoritative person-scoped identifier with compatible kind and no conflict | Name similarity at least 0.80, with issuer/employment/jurisdiction context recorded; a shared name or employer cannot auto-consolidate |
| Security | 1.00 for exact unique authoritative instrument identifier under approved interval/scope | Issuer/title or CUSIP-only ambiguity is review evidence; no fuzzy automatic consolidation |
| Branch, Government Entity, International Organization | 1.00 for exact unique identifier under that kind's approved authority | Conflicting or non-authoritative mappings require explicit review; no numeric fuzzy fallback |
| Market/Venue | 1.00 for exact MIC within approved identity and effective scope | Code changes, segment/operator ambiguity and code reuse require review |
| Fund Structure | 1.00 for exact identifier proved authoritative for that structural level | PFID/LEI/series aliases require explicit compatible-form evidence; name/adviser similarity alone is review |

Automatic threshold is exactly 1.00. A unique existing source-record binding
permits an update to that subject but still rechecks corrected identifiers and
kind; it is not a permanent exemption from matching. Multiple exact candidates
are a conflict requiring review. Fuzzy ties do not select an identity by UUID.

Normalize names with a versioned Unicode normalization, case-folding and
whitespace policy; preserve original text. Pin the similarity dependency and
algorithm. Missing implementation is a hard failure, not the current optional
length-based fallback in `match.py`. Scores rank review candidates; they are
not probabilities of identity. Raising automatic coverage requires labeled
positive/negative cases including homonyms, reused identifiers, and mixed kinds.

No eligible candidate yields a new provisional source subject. Publication
requires an authoritative identity anchor or an evidence-bound acceptance
decision; low-score/no-identifier input remains reviewable evidence. A role
identifier may bind a profile to an already accepted identity only when its
authority establishes the holder and kind. A 13F filing alone does not prove
regulated Adviser status.

## Determinism and surviving IDs

Derive each source-subject seed UUID from one fixed, versioned UUID namespace
and canonical `(kind, source_code, immutable subject key)` encoding. The
subject key remains stable through that source's corrections; a filing-local
occurrence may remain a separate anchor until a decision binds it.

An accepted merge forms a same-kind component of source anchors. Its survivor
is the lexicographically smallest seed UUID; other IDs resolve through dated
aliases. Never use random creation order, `created_at`, name, or last arrival.
Adding a lower seed can change the canonical ID; publish explicit replacement
and alias records and retain all accepted prior IDs. During rebuilding, freeze
the complete baseline before exposing IDs to consumers.

Identity decisions, source supersessions and retractions are inputs to replay.
For the same complete evidence set, accepted decisions and policy versions,
record/batch arrival order must not change final identity components, winners,
current relationship set, aliases, or business hashes. Operational attempts
and observation history can differ. Freeze candidate generation against the
declared evidence watermark; ambiguous candidates remain unresolved rather
than inheriting a first-arrival decision. Differential tests must compare
final results across permutations, duplicates and batch boundaries.

## Field semantics

| Input state | Effect |
| --- | --- |
| Omitted field | No assertion; existing source contribution is unchanged for patch datasets |
| Unknown / JSON null | Unknown evidence, ineligible to overwrite a known value |
| Explicit typed value | Eligible according to field authority and validity |
| Authorized clear | Eligible tombstone that can win and suppress fallback; allowed only for declared fields/sources |
| Retract assertion | Withdraw that source contribution and recompute from remaining eligible evidence |
| Complete-scope retirement | Withdraw only the scoped source contribution after completion proof; does not delete the identity or history |

Full-record datasets must explicitly specify whether omission means unknown
or retraction. There is no universal “missing means delete.” A clear needs a
reason and source authority. Neither a clear nor a source retirement physically
deletes evidence. Empty string normalization is a per-field schema rule.

First find the latest applicable version of each source record at the target
valid time using native revision/supersession semantics. Then select among
eligible sources by this total order:

1. Active evidence-bound stewardship override for that field/scope, if any.
2. Versioned source rank for `(identity kind, optional profile type, field)`.
3. Descending source effective time, with missing time sorted last.
4. Descending publication time where the field policy permits it.
5. Stable dataset code, source-record key, and assertion digest ascending.

Native correction order is applied within a dataset/record chain, not compared
as a meaningless ordinal across providers. Equal ranks resolve eligible
ordinary-field disagreements deterministically while preserving a conflict
record. Authoritative identity disagreement cannot be settled this way.

Fields without a registered policy remain evidence-only. Initial authority
families are SEC for CIK and SEC-reported issuer/filing facts, IAPD/ADV for
adviser registrations and reported private-fund facts, accepted PCAOB evidence
for its audit registration identifiers, and GLEIF for its LEI/legal-record and
exact relationship assertions. Separate namespaced reported values avoid
pretending those authorities have identical meanings. Each publication adapter
must enumerate actual fields and priorities before its implementation ticket.

Steward overrides are new governed assertions with reviewer, reason, evidence,
scope and expiry/revocation, never direct domain-table patches. A winning field
exposes assertion ID, policy digest, origin run, reason, and losing candidates.

## Relationships and reversal

Retain immutable asserted endpoints and their original source subject anchors.
Derive current endpoints through accepted bindings. Merge does not rewrite
source claims. Reproject all affected relationships, coalescing only identical
business relationships while retaining every supporting assertion. Validate
kind/profile, intervals, self-links, hierarchy cycles and parent conflicts
again before creating durable publication intent.

Each merge event records all anchors/aliases, prior bindings, decision evidence,
policy digest, affected relationships and projection revisions. Reversal is
a new steward-authorized event referencing that merge, not a deletion:

1. Fence the affected identity/relationship closure and materialize a preview
   with before/after identities, fields, aliases, edges and consumer changes.
2. Remove the revoked merge from the accepted-decision graph and find dependent
   merge decisions. Decisions that used the invalid combined identity require
   re-adjudication; independent evidence-backed decisions remain valid.
3. Replay retained assertions and later corrections with explicit policy
   versions. Partition by source attribution; unassignable later manual facts
   return to review instead of being guessed onto one restored identity.
4. Commit restored partitions, binding history, revised projections, reversal
   evidence, checkpoint and compensating publication intents atomically.
5. Verify consumers at the new generation before reporting reversal complete.

If the closure exceeds a bounded transaction, build and verify it in an
isolated generation using bounded batches, then atomically activate the full
generation. Readers cannot observe a partly reversed identity graph. Policy
upgrades are separate explicit replay operations, not implicit behavior during
reversal. Source evidence and lineage survive every step.
