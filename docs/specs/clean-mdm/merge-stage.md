# Shared Merge Stage

Status: accepted policy v1; governed by the
[Wayfinder decision](../../../.scratch/clean-mdm/issues/01-set-merge-stage-policy.md).
Revised after [vendor research](../../research/clean-mdm-vendor-merge-rules-2026-09-17.md).
The earlier numeric thresholds and smallest-seed survivor rule are withdrawn.
Q1–Q15 were accepted on 2026-09-18: validated binding, steward-approved
consolidation, field authority/groups, clear/retract semantics, override lifetime
and evidence-based reversal with Match Exclusion, stable internal IDs, indefinite
overrides when no expiry is supplied, and review of dependent merges before
reversal activation. The earliest-published survivor default, 99.9% precision
release target and Fund Structure/Branch/Government/Venue boundaries are now
accepted. Actual score calibration remains unproven. Accepted Q16 permits the local build
with every unqualified exact/scored automatic rule disabled. Measured calibration
and versioned policies gate each rule's activation, not implementation tickets.

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

Source Record Binding and Identity Consolidation are separate authorities
inside the Merge Stage. Accepted first-release boundary: validated rules may
bind an incoming source to one accepted identity; consolidating two established
identities requires an explicit steward decision. A bridge between several
eligible identities goes to review without attaching to an arbitrary winner.

| Kind | Candidate identity evidence | Required guard |
| --- | --- | --- |
| Company | Authoritative CIK/LEI/jurisdictional registration; name/address/jurisdiction comparisons | Compatible legal kind, whole-group identifier consistency, measured exact/scored-rule behavior |
| Person | Person-scoped authoritative identifier; name and documented context | Shared name or employer alone is insufficient; no Company comparison |
| Security | Instrument identifiers with approved interval/scope; issuer/title context | Ambiguous CUSIP or issuer/title is not a unique instrument identity |
| Branch, Government Entity, International Organization | Approved identifiers and evidence for the specific kind | No generic fuzzy fallback without a domain-specific validated contract |
| Market/Venue | MIC with identity and effective scope | Operator/segment ambiguity and code reuse need review |
| Fund Structure | Identifiers with evidence for the precise structural level | No name/adviser-only collapse of PFID, LEI, series or share-class meanings |

No universal automatic or review score is specified. Accepted Q11 requires
at least 99.9% precision, demonstrated by a one-sided 95% lower confidence bound
on representative, independently labeled held-out automatic-binding decisions
for each enabled entity kind and rule family. Insufficient evidence keeps a
rule review-only. Also require zero hard-veto violations in adversarial fixtures;
measure candidate recall and review volume. This statistical release target is
not a similarity cutoff or an accuracy guarantee. Actual cutoffs require measured
calibration and a versioned policy before automatic activation; none have been
validated yet. A unique existing source binding permits an update but still
checks corrected identifiers and kind; changes that dispute identity
create review rather than silently moving the record. Multiple exact candidates
are a conflict. Fuzzy ties do not choose an identity by UUID.

Normalize names with a versioned Unicode normalization, case-folding and
whitespace policy; preserve original text. Pin the similarity dependency and
algorithm. Missing implementation is a hard failure, not the current optional
length-based fallback in `match.py`. A rule's similarity score is not itself
a probability of identity. Validation includes homonyms, reused identifiers,
mixed kinds and transitive bridges, for both automatic binding and review.

No eligible candidate yields a new provisional source subject. Publication
requires an authoritative identity anchor or an evidence-bound acceptance
decision; low-score/no-identifier input remains reviewable evidence. A role
identifier may bind a profile to an already accepted identity only when its
authority establishes the holder and kind. A 13F filing alone does not prove
regulated Adviser status.

## Determinism and surviving IDs

Accepted rule: once an identity is published, adding or correcting source
evidence does not change its ID. Source-record keys remain distinct from
master IDs and stable through source corrections. An approved consolidation
explicitly selects an existing survivor; the losing published ID becomes a
versioned alias. Accepted Q10 defaults to the earliest published identity,
using UUID ordering only for equal publication times. A steward may select
another existing ID with a recorded reason. Retain the publication history and
selection decision for replay; arrival order never replaces that history.
Survivor selection does not determine which source wins any master field.

The persistent identity registry, bindings and accepted decisions become
explicit replay inputs alongside evidence, supersessions, retractions and
policy versions. Replays with those same inputs must reproduce IDs, identity
components, winners, current relationships, aliases and business hashes across
record permutations and batch sizes. Operational attempt history may differ.
Freeze candidate generation against the declared watermark; ambiguous bridges
remain unresolved rather than inheriting a first-arrival decision.

A fresh rebuild from source bytes alone cannot be called exact-ID replay under
this accepted policy. It either restores the approved registry/decision history
or proves semantic parity through a verified crosswalk. The initial isolated
rebuild must establish and retain its registry before publishing IDs. This
accepted tradeoff replaces the earlier smallest-seed rule.

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

Accepted policy: declare coherent field groups, such as address components,
that must select one source assertion together. Keep type-plus-field priorities
for independent facts. Validate source eligibility, quality and any declared
freshness limit at the pinned as-of time before ranking. Do not mix address
parts from different claims without a separately evidenced transformation.

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
Accepted lifetime rule: contradictory source updates open review while the override
persists until its declared expiry or explicit revocation. Without an explicit
expiry it remains until revoked; do not invent automatic expiry schedules.
A field contract may declare a specific expiry policy before activation.

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
   re-adjudication before reversal activation; do not guess their new partition.
   Unrelated identities continue processing. Independent evidence-backed
   decisions remain valid.
3. Replay retained assertions and later corrections with explicit policy
   versions. Partition by source attribution; unassignable later manual facts
   return to review instead of being guessed onto one restored identity.
4. Commit restored partitions, binding history, revised projections, reversal
   evidence, checkpoint and compensating publication intents atomically.
5. Verify consumers at the new generation before reporting reversal complete.

Accepted policy: record a scoped Match Exclusion so the next replay cannot
automatically recreate the rejected merge. Revocation requires a new
evidence-bound decision; the exclusion must not block unrelated identities.

If the closure exceeds a bounded transaction, build and verify it in an
isolated generation using bounded batches, then atomically activate the full
generation. Readers cannot observe a partly reversed identity graph. Policy
upgrades are separate explicit replay operations, not implicit behavior during
reversal. Source evidence and lineage survive every step.

## Q16 implementation boundary — 2026-09-18

The user accepted starting the offline build with unqualified automatic rules
disabled. This supersedes earlier pre-implementation calibration timing above.
Q1–Q16 are accepted; numeric calibration and versioned policy evidence are
mandatory before each automatic rule activation. Implementation is authorized;
production activation still requires all local and hosted acceptance gates.
