# SEC + GLEIF Company policy — accepted interview decisions

Date: 2026-09-19. The user accepted Company Q1–Q12, one question at a time,
after PR #657 merged. These decisions supersede conflicting earlier Company
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

## Preserved decisions

The original statistical gate continues to govern each automatic source-binding
rule family independently. Similarity scores are not calibrated probabilities;
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

## Remaining design gate

Claude's persisted pre-merge candidate proposal has been reviewed in
[handoff reconciliation](design-reconciliation-2026-09-19.md). The remaining
question is whether to retain an assessment before **every new binding and
published-ID consolidation**, or only for deferred/review candidates.
Recommendation: every identity proposal, with immediate automatic progression
when qualified; field-only refreshes keep the existing evidence/effects path.
This assessment coverage recommendation is not yet user-accepted.
