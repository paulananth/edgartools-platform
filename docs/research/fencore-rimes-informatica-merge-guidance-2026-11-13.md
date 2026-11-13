# Merge design guidance: Fencore, Rimes/Matrix IDM and Informatica

Research date: 2026-11-13. Status: guidance, not an accepted rule change, product selection or runtime qualification. Public first-party sources were researched; no vendor runtime was tested. Repository baseline: `9b00663adb4dc859be5ac21be31b75248e2fb9cd`.

## Recommendation

Retain the shared Merge Stage for Company, Person and Security. Configure separate entity policies and separate three decisions: whether records describe the same entity, whether existing golden identities may consolidate, and which contributed values win. Vendor publications support these business distinctions; they do not reveal whether each vendor internally uses one implementation or separate services.

## What the vendors actually publish

| Product and evidence level | Published design | Boundary of the evidence |
| --- | --- | --- |
| Fencore DataHub: product overview | Configurable model and mastering; matching plus source priority and field-level transforms/validation; cell-level lineage, audit, ownership and multi-eye approvals. Data quality, mastering and reconciliation are distinct activities. | Public overview does not specify match algorithms, tie-breaking, transitive cluster rules, survivor IDs or unmerge semantics. |
| Rimes Data Management: product overview | Ingests, validates, enriches and governs investment data; establishes lineage at ingestion; harmonizes security, price and entity masters and mappings. | Does not publish identifier precedence, thresholds, field-survivorship ties, conflict vetoes, or reversal mechanics. These remain unknown, not absent. |
| Rimes Matrix: product positioning | Matrix is described as a cloud-native investment intelligence platform for storing/analyzing investment data and look-through. | Do not attribute Rimes' broader mastering capabilities or a private merge algorithm specifically to Matrix IDM. |
| Informatica Multidomain MDM SaaS: vendor explanation | Declarative and learned matching; match explanations; high-confidence automatic merges and review for uncertain matches. Attribute-level trust chooses field values and is reapplied on source updates and unmerge. | Published capabilities do not establish our identifier authority rules or acceptable false-merge rate. |
| Informatica MDM Hub 10.5 HF4: product documentation | Exact-match and fuzzy-match base objects; fuzzy objects may use exact, fuzzy or combined match columns. | Hub and SaaS have different versions and contracts; do not transfer implementation details between them. |

Sources for the table, checked on the research date:

- [Fencore DataHub full overview, Quality/mastering/reconciliation and Model/governance](https://www.fencore.co/products/datahub/full).
- [Rimes Data Management, Reduce operational burden](https://www.rimes.com/solutions/data-management/).
- [Rimes fact sheets, Matrix positioning](https://www.rimes.com/rimes-fact-sheets-investops-europe-paris/); [Rimes acquisition/rebrand context, April 2022](https://www.rimes.com/rimes-launches-global-rebrand-in-support-of-growth-strategy/).
- [Informatica SaaS, Master Data Match/Merge/Survivorship](https://www.informatica.com/blogs/powering-digital-business-with-intelligent-multidomain-master-data-management-saas.html).
- [Informatica Hub 10.5 HF4, Exact-match and Fuzzy-match Base Objects](https://docs.informatica.com/master-data-management/multidomain-mdm/10-5-hotfix-4/configuration-guide/part-4--configuring-the-data-flow/mdm-hub-processes/match-process/exact-match-and-fuzzy-match-base-objects.html).

Informatica's [SaaS development learning path](https://success.informatica.com/learning-path/mdm-saas/development.html) explicitly separates match-model configuration from survivorship/source ranking, and describes automatic merge, manual review and unique-record outcomes. Its [trust/survivorship configuration offering](https://success.informatica.com/success-accelerators/psu/mdm-trust-and-survivorship-configuration-support.html) also names block survivorship, validation and decay. These establish available concepts, not an obligation to adopt numerical trust or aging for every field.

Access limitations: direct retrieval of the Hub trust-settings page returned HTTP 403; the SaaS survivorship FAQ opened as a CSS-error shell despite indexed text. Neither is used to assert an exact precedence algorithm here. This report does not reproduce their indexed tie-break sequence. No reviewed public source establishes a universal authoritative-identifier veto or persistent cannot-link semantics shared by all three vendors.

## Guidance for this repository — our design recommendations

The recommendations below are inferences from the published concepts and repository code, not claims about vendor internals.

### 1. Keep the three decisions separate

```text
captured source → configured reading → source assertion(kind, evidence, revision)
    → retrieve same-kind candidates
    → matching policy: join / create / wait / review
    → explicit permission before consolidating existing golden identities
    → field/profile selection from eligible contributions
    → destination validates and commits effects, history and progress atomically
```

This is a conceptual boundary, not a proposed reorder of the current engine. A source assertion attaching to one existing master and two existing masters consolidating are different business actions. A rule that permits the first must not implicitly grant the second. An issuer relationship is not evidence that Company and Security are the same entity.

The existing worker already groups assertions by kind and calls one merge function ([worker](../../edgar_warehouse/workers/mastering_merge.py#L90)). The shared identifier path reads configured contracts, retrieves holders and filters by kind ([merge](../../edgar_warehouse/mastering/merge.py#L260)); consolidation follows its configured decision rather than a separate entity-specific merge class.

### 2. Finish configuration before adding engine code

For every entity/source route, document identifiers and their authority, identifier versus cross-reference status, candidate selectors, conflict checks, missing/multiple-match outcomes, consolidation permission, field source order, freshness and clear/retract handling. Record which behavior is already supported, which needs configuration, and which genuinely needs a shared primitive.

The existing Rust field-selection code already supports defaults, field overrides and grouped field authority ([field_values.rs](../../crates/source-contract/src/field_values.rs#L35)); it also interprets source eligibility, clear permissions and freshness ([selection](../../crates/source-contract/src/field_values.rs#L112)). Audit and reuse those capabilities before proposing new trust scores or group-selection machinery. Source rank is a starting policy; later arrival alone must not make a source authoritative. Select related values together where independently winning fields would make an impossible combination.

### 3. Apply different policies to the three entities

| Entity | Configuration work to prioritize | Required counterexample |
| --- | --- | --- |
| Company | Review CIK/LEI/CRD authority and lookup-only routes; retain identifier-first matching and the existing evidence-qualified name-pair path. Define field authority and freshness by source and field group. | Similar names with contradictory authoritative identifiers must not silently consolidate; an ambiguous name remains reviewable. |
| Person | Review classification and CIK routes across submissions and ownership; retain source assertions and field provenance. Add name-based matching only for an evidenced use case with sufficient independent discriminators. | Two people with the same name remain separate; a Company and Person sharing an identifier never join across kinds. |
| Security | Review CUSIP/ISIN/listing-FIGI/share-class-FIGI roles, lookup-only symbols and source-specific fallback keys. Preserve configured conflict and consolidation distinctions. Keep issuer links and listing details explicit. | Shared ticker or share-class information must not authorize an unintended consolidation of distinct instruments. |

These priorities review the committed [Company](../../rules/merge/kinds/company.yaml), [Person](../../rules/merge/kinds/person.yaml) and [Security](../../rules/merge/kinds/security.yaml) policies. They are not new production matching rulings. No source-level activation is inferred from a rule's presence.

### 4. Extend only the specialized boundary that needs reuse

The current name-pair path explicitly reads and writes LEIs ([merge.py](../../edgar_warehouse/mastering/merge.py#L351)). If another required matching workflow needs the same operation for a different identifier, extend the existing matching profile to carry the namespace, evidence paths and conflict check. Keep the current LEI behavior as the first compatibility fixture. Do not create CompanyMerge, PersonMerge and SecurityMerge implementations, or a general-purpose plugin framework without a demonstrated need.

### 5. Make results explainable and reversible

For each selected field, expose its source assertion, effective time and selection policy; show why alternatives lost. For a merge/review/override decision, retain the rule version, evidence, actor where applicable and reason. Ordinary identifier joins may remain represented by the existing source-to-master binding: auditability does not require reinstating a separate decision row for every plain join ([current binding behavior](../../edgar_warehouse/mastering/merge.py#L312)).

Prove reversal after later source updates, not only immediate undo. Define redistribution of assertions, identifiers, relationships and aliases, plus consumer notifications. A data steward's deliberate split must not be silently undone by the next automated match. These are our acceptance obligations, not publicly established cross-vendor guarantees.

## Delivery order and acceptance

1. **Configuration inventory:** one matrix covering every current source route for all three kinds; no provider acquisition. Refresh the baseline and related open work before implementation.
2. **Policy completion:** fill evidenced configuration gaps and regenerate mapping documents; keep every behavior change distinct from an abstraction-only change.
3. **Narrow engine extension, only if needed:** GoF consultation and compatibility cases first; shared Rust/Python interpretation, destination-enforced transactions and uniqueness retained.
4. **Proof:** explicit expected answers for create, join, review, wait/release, field conflicts, correction, unchanged replay, split exclusion and failure rollback. Cover source-specific routes, not just one generic happy path. Include bridge cases where A matches B and B matches C but A conflicts with C; similarity must not bypass cluster-wide conflicts.
5. **Review and release:** Standards/Spec/GoF, affected installed caller checks, then bounded source proving runs. Qualification, approval and activation remain separate. No new hosted environment is selected by this research.

The cheapest first deliverable is the configuration/behavior matrix and its existing-test coverage map. Source priority, grouped values, indexed candidates and the shared engine already exist; vendor research does not justify rebuilding them. Broad fuzzy or ML auto-merging should wait for a measured use case with labeled difficult negatives and an explicit false-merge tolerance, rather than copying a vendor's marketing accuracy figure.

## Questions public material cannot settle

If implementation-level vendor comparison becomes necessary, request a worked demonstration of: conflicting authoritative IDs; transitive matches with a conflicting third record; equal-priority values and null/clear behavior; source correction after consolidation; split followed by replay; issuer/listing reassignment; concurrent conflicting updates. Require inputs, expected outputs, evidence and product/version. No vendor contact or demo request was made in this research.
