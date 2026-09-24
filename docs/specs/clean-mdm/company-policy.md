# SEC + GLEIF Company policy — accepted interview decisions

Date: 2026-09-19; Q14 accepted 2026-09-20. The user accepted Company Q1–Q13,
one question at a time, after PR #657 merged, then accepted deterministic
identifier binding in Q14. These decisions supersede conflicting earlier Company
recommendations; they are requirements, not implementation or calibration proof.
The original Clean MDM Q1–Q16 numbering is a different interview.

| Company question | Accepted decision |
| --- | --- |
| Q1 | Cover the SEC Company universe plus approved GLEIF-only parent Companies needed for accounting hierarchies; do not expand to all global GLEIF Companies. |
| Q2 | A verified GLEIF no-match is a completed outcome. Publish the SEC-backed Company; ambiguous candidates cannot contribute GLEIF fields. |
| Q3 | Freeze the existing tracked eligible SEC Company universe in a versioned CIK manifest, including eligible inactive Companies and their history. Newly tracked Companies enter the incremental pipeline afterward. |
| Q4 | Automatic approval is the default. Use qualified fuzzy matching with corroborating identifiers, jurisdiction and address evidence. Human intervention is reserved for necessary exceptions. This explicitly replaces the proposed user/manual approval default. |
| Q5 | Source-record binding and consolidation of existing published Company IDs use separate confidence/authority gates. |
| Q6 | Automatically defer ambiguous GLEIF matches and continue SEC-backed publication. Preserve candidates/reasons and retry when source evidence or rules change. Report affected GLEIF enrichment as incomplete. |
| Q7 | Automatically create verified, Company-eligible GLEIF parent identities after matching against existing Companies. Reuse an accepted identity; create a new immutable ID only when no unresolved candidate remains. Unsupported kinds remain evidence. |
| Q8 | Resolve ordinary comparable field disagreements using versioned field-specific source priorities. Preserve both values, provenance and disagreement. Keep different concepts in separate fields. Identity contradictions still veto linking. |
| Q9 | An authoritative identity contradiction suspends the affected established link and rebuilds from remaining trusted evidence. Preserve the Company ID, history and recovery lineage. A name change or lapsed registration alone is insufficient. |
| Q10 | Automatic consolidation of two published IDs requires a verified shared authoritative identifier and no conflicting authoritative identifiers across the entire component. Fuzzy similarity alone is insufficient. |
| Q11 | Independently qualify automatic consolidation to the same accepted 99.9% precision target, demonstrated by a one-sided 95% lower confidence bound, plus zero hard-veto violations in adversarial tests. Exact matching has no exemption. Unqualified consolidations defer while other qualified work proceeds. |
| Q12 | The local Company milestone may complete with audited linked, verified-unmatched and deferred outcomes for every scoped Company, provided qualified multisource matching is demonstrated and required source, recovery and publication checks pass. Report deferrals explicitly; do not claim full enrichment. |
| Q13 | Retain a durable pre-commit assessment for every proposed binding and published-ID consolidation, including automatic proposals. Qualified proposals proceed immediately; field-only refreshes keep their existing evidence path. |
| Q14 | Use the rules-as-data design. Identifier-only source binding may activate through a verified, versioned Identifier Contract without a separate statistical precision qualification. An exact identifier resolving to one compatible existing Company automatically reuses that immutable Company ID. Conflicts defer; fuzzy binding and published-ID consolidation retain their separate statistical qualification gates. |

## Confidence bands — accepted 2026-09-24

The operator set how a Company decision acts on its probability. **Probability**
here is how often the rule step that made the decision is right, measured in
testing (the Proving Run) and stated as a one-sided 95% lower bound. It is
never a score invented at runtime.

| Probability the decision is right | What happens |
| --- | --- |
| **95% or more** | Acts automatically. No Steward. |
| **50% to below 95%** | Waits in the Stage with no kind or link. No Steward. It is tried again when the rule improves and is tested again. |
| **Below 50%** | Marked for a Steward. Only these records wait for a person. |

It applies to two decisions:

- **Classification**: is this identified entity a Company?
- **SEC-to-GLEIF source binding**: is this SEC Company the same as this GLEIF
  record (ticket 08)?

**What this changes.** The automatic bar for these two decisions falls from
99.9% to **95%**. That replaces the 99.9% Company bar for them in company
mastering ticket 02 (decision 4) and ticket 08. **Public data is not vetted by
a person as a routine step**: a weak rule is caught in testing and fixed,
not reviewed one record at a time. That narrows Q4's "necessary exceptions" to
the below-50% band.

**What it does not change.** Consolidating two already-published Company IDs
keeps Q10/Q11's 99.9% bar. Identifier-only binding keeps Q14's contract
verification, with no statistical bar.

## Preserved decisions

The original statistical gate continues to govern each automatic fuzzy
source-binding rule family independently. Q14 supplies a separate deterministic
activation path for identifier-only binding. Similarity scores are not calibrated probabilities;
no arbitrary universal cutoff is accepted. The previous 308 adjudicated seed
links require revalidation and are not independent held-out qualification truth.

Preserve permanent IDs, earliest-published default survivor and aliases,
Match Exclusion, evidence-bound reversal and review when dependent reversal
cannot safely determine a partition. Preserve typed accounting/ownership and
reported/calculated relationships, SEC authority over filings/financial facts,
and GLEIF's approved first-slice fields. OpenCorporates mapping corroborates
identity; it is not independent merge authority.

Local PostgreSQL 16 remains the current target. MDM master/journal/outbox share
`mdm`; acquisition history remains in `change_ledger`, which also receives a
durable mirror of committed MDM events. Bookkeeping retains the single root
run. Required publication receipts cannot
be waived to make a run pass. Hosted qualification/cutover remains separate;
the legacy rollback period is 30 days after eventual cutover.

## Completion states must remain distinct

A valid parsed Company whose match is ambiguous can receive an audited
`deferred_match` outcome without holding up unrelated Company publication.
This does not authorize ignoring malformed source bytes, unverified/missing
publication members, unaccounted source records, unresolved hard identity
integrity failures, or missing required consumer receipts. Their prerequisites
and recovery contracts still have to pass.

The frozen manifest, policy version, source inventory, matched/unmatched/
deferred counts, affected Company IDs, reasons and retry triggers must make
the boundary checkable. A run that merely defers everything without qualified
multisource proof does not establish this milestone.

## Assessment coverage — accepted Q13

Claude's persisted pre-merge candidate proposal has been reviewed in
[handoff reconciliation](design-reconciliation-2026-09-19.md). The user accepted
Q13 on 2026-09-19: retain an assessment before **every new
binding and published-ID consolidation**, including automatically approved
proposals. Qualified proposals progress immediately; field-only refreshes keep
the existing evidence/effects path. No manual approval gate is introduced.

## Deterministic binding — accepted Q14

On 2026-09-20 the user selected Identifier Contract activation for identifier-only
binding and rejected requiring the statistical matching gate for routine reuse
of an established master. This is the Company-specific acceptance of the
deterministic path in Claude's [policy-language proposal](../mdm/policy-language.md).

Declare the namespace, issuing authority, normalization and primitive versions,
scope/cardinality, compatibility checks and verification evidence in the pinned
policy. Verify the contract to activate the rule; do not require a new precision
study or manual approval for every later exact-match source record. Record the
automatic binding's assessment and rule/contract evidence through Q13 and the
shared transaction boundary.

An identifier match must resolve to one compatible Company. Missing, ambiguous,
conflicting, suspended or unsupported identifier evidence does not gain binding
authority. Identifier values from different namespaces are not interchangeable;
an LEI does not establish a CIK crosswalk merely because both values exist.
Names and lapsed registration alone do not revoke established bindings (Q9).

This changes the activation evidence for identifier-only **source binding**.
It does not exempt merging two existing published IDs from Q10/Q11, qualify a
fuzzy rule, approve the old 308 seed links, or import Person-specific tolerance
measurements into Company policy. Required publication receipts still govern
end-to-end completion. The runtime's blanket `automatic_rules` refusal must be
replaced by implemented and tested activation predicates before any rule runs
automatically; this decision is not evidence that the interpreter is installed.
