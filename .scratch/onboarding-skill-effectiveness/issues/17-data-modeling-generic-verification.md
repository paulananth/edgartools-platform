# data-modeling: Specify generic verification

Type: task
Status: resolved
Priority: P0
Blocked by: 05, 11, 16
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)
Skill: [data-modeling](../../../skills/data-modeling/SKILL.md)
Step: 5 of 6
Skill dependencies: data-profiling
Applicability: Every new part whose class, identity, relationship or destination needs mapping.

## Question

Which complete behavioral scenarios prove this skill's claims, using shared tooling and source-supplied fixtures rather than copied source-specific logic?

## Scope and evidence

Propose Given–When–Then scenarios before writing test code and obtain the operator's required scenario approval. Start with: a shared issued identifier, an ambiguous name, a cross-reference-only identifier and an effective-dated relationship.

Required observable proof: keep ambiguous names apart, distinguish identity from lookup and assign entity attributes and transaction facts to their governed owners. Reuse existing generic workers, fixtures and harnesses; configuration and invented input data supply source differences. If tooling cannot express a behavior, link a separate capability-gap ticket rather than adding source-specific runtime code here.

Start from skills/data-modeling/SKILL.md: Decision rules, Workflow, Prove the model on the data before building. Read current main and installed skill provenance before changing anything; repository and installed copies may differ.

## Prerequisites

[data-platform: Specify generic verification](./05-data-platform-generic-verification.md); [data-profiling: Specify generic verification](./11-data-profiling-generic-verification.md); [data-modeling: Make progress resumable](./16-data-modeling-resume.md)

Priority rationale: Identity and destination decisions precede configuration.

These blockers order skill-improvement work. They do not activate optional source phases or grant operational permission.

## Acceptance checklist

- [x] Record and obtain operator approval for the four [Given–When–Then scenarios](#approved-scenarios) before writing tests. Operator selected “Approve as written.” (2026-11-24 21:18 ET)
- [x] Exercise all four approved scenarios through shared behavior paths: six invocations on disposable PostgreSQL 16, including both arrival orders and separate relationship and Silver proofs. (2026-11-24 21:18 ET)
- [x] Record persisted outcomes, projection evidence and limits under [Answer](#answer). No mock supplied any asserted matching, period or storage outcome. (2026-11-24 21:18 ET)
- [x] Publish the scoped proofs in [test(modeling): prove identity, stated periods, and fact ownership](https://github.com/paulananth/edgartools-platform/pull/2127); six behavioral invocations and **155** documentation genericity checks passed locally. (2026-11-24 21:19 ET)
- [x] Learning → skill: none. The proof exercises decisions already in the Data Modeling skill without changing rules, the skill or runtime behavior. (2026-11-24 21:18 ET)

## Completion evidence

Record the answer and artifact links under `## Answer` when resolved. Keep private values out of the public record. A not-applicable phase needs evidence and an explicit applicability disposition, not a false PASS. Do not mark this ticket resolved while a checklist item remains open.

## Approved scenarios

1. **Shared issued identifier.** Given two invented Company records from different sources with the same issued identifier in a namespace that the Mastering Policy allows both sources to match on, when both sources are mastered in each arrival order, then both source records bind to one Company and the identifier remains on that Company. Compare membership and held identifiers, not independently allocated master IDs.
2. **Ambiguous name.** Given two Companies with different issued identifiers but the same normalized name and a third record with only that name, when the configured exact-name matching rule sees both candidates, then the two Companies stay separate, the third record binds to neither, no third Company is minted, and the ambiguity is recorded for review.
3. **Lookup-only identifier.** Given two Securities with different matching identifiers and the same cross-reference in a namespace no matching rule covers, when they are mastered and the shared value is queried, then two distinct masters remain and the reader reports multiple holders rather than choosing one or joining them.
4. **Effective-dated relationship and fact ownership.** Given a source assertion with an explicit relationship period that differs from its publication date, when the configured contract and relationship projection process it, then the typed relationship keeps the declared endpoint direction and its stated start/end without taking dates from the publication. In a separate Silver proof, given an entity attribute and a transaction amount about that entity, when the configured writer lands the fact, then the attribute is available in MDM, the amount stays on the Silver fact at its own grain with the declared link, and the Silver fact does not copy the master attribute.

Use invented fixtures and shared engine and writer paths. Start with existing behavior tests; implement only coverage they do not already provide. Record which outcomes were checked in storage and which only through projection. No provider requests, real-source operations, or source-specific runtime changes.

## Answer

| Approved scenario | Observed outcome on invented inputs | Proof |
|---|---|---|
| Shared issued identifier | In both arrival orders, the two source records bound to one persisted Company holding the same LEI. | `test_two_sources_with_the_same_issued_lei_bind_to_one_company` |
| Ambiguous name | Two Companies remained in MDM. The name-only record bound to neither, minted no third Company, and created an ambiguity review. | `test_a_name_held_by_two_companies_goes_to_review_and_joins_neither` |
| Lookup-only identifier | Two Securities remained distinct; the context reader rejected single-entity resolution and reported two holders of the cross-reference. | `test_a_cross_reference_two_masters_share_is_not_settled_for_the_reader` |
| Effective dates and fact ownership | The configured relationship contract and projection over persisted claims returned one directed relationship with its stated start and end, not the publication date or accounting period. Separately, a stored custody fact retained its filing/row grain and exact amount and resolved its custodian through `master_binding`. The custodian name remained in MDM, not on the fact; the amount was not a master field. | `test_stated_relationship_period_survives_projection_from_persisted_claims`; `test_the_custody_fact_links_to_the_master_without_copying_its_name` |

### Verification and limits

- Focused `pytest --testmon --testmon-noselect` invocations against disposable PostgreSQL 16: the shared-ID order cases, ambiguous name, lookup-only ID and Silver fact passed together (**5 passed**). The configured relationship parser initially rejected the new fixture's invalid check digits; after correcting only those invented digits, the focused period case passed (**1 passed**). No runtime fix or weaker assertion was needed.
- The relationship result is a calculated projection over database-backed evidence, not a test of publishing relationship rows. The Silver case is a separate persisted fact proof, not a single source workflow covering all four scenarios. No providers, live data, hosted stores or additional database dialects were exercised locally.
- Exercised repository Data Modeling guidance at base `e8865856`, with `SKILL.md` blob `797263c0056f455447d14b002c227152d0380491`. Neither installed modeling copy was available.
