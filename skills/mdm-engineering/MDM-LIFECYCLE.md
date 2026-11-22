# MDM implementation and merging lifecycle

Read this when planning an MDM implementation, assigning stewardship, comparing
operational and analytical consumption, or locating a rule change in the whole
flow. MDM combines people, process and technology. Follow `CONTEXT.md` for this
platform's definitions; the implementation details remain with the linked owners.

## Seven implementation steps

| Step | Decision and evidence | Owner and completion |
| --- | --- | --- |
| 1. Establish governance | Definitions, quality requirements, sensitivity, permitted use, access and who may approve changes. | Governance leaders and policy specialists use [Data Governance](../data-governance/SKILL.md) and [Data Catalog](../data-catalog/SKILL.md). Record agreed meanings, controls and authority; a guide does not itself grant permissions. |
| 2. Define domains and models | Determine each part's class, kind, identity, fields, relationships, hierarchy, grain and time from approved profiling. | Architects/modelers use [Data Profiling](../data-profiling/SKILL.md) then [Data Modeling](../data-modeling/SKILL.md). Configure the accepted model; request shared schema/adapter work here only where configuration cannot express it. |
| 3. Integrate evidence | Capture and retain source bytes and provenance; map source keys and fields through contracts before loading MDM and Silver. | Integration engineers use [Data Onboarding](../data-onboarding/SKILL.md) for new feeds and [Data Operations](../data-operations/SKILL.md) for execution. Acquisition needs its existing authorization; readers consume captures without provider requests. |
| 4. Profile, validate and match | Profile before configuration, enforce input checks at reading, and apply approved identity/matching rules. Version reference-code interpretations. | Profiling, [Data Quality](../data-quality/SKILL.md) and this skill's [refinement procedure](REFINING-RULES.md). Show measured quality and matching outcomes; similar names alone are not identity evidence. |
| 5. Resolve exceptions | Keep ambiguous identities unjoined or waiting with review evidence; a steward resolves the supported case through the application. | Data stewards record actor, reason, evidence and policy version. New identities follow the kind's creation rule; not every new record requires review. Source/review evidence can persist while an unsafe identity effect is withheld. |
| 6. Govern relationships | Define typed endpoints, cardinality, hierarchy constraints, effective dates and supported lifecycle changes. | Modeling defines meaning; refinement configures supported rules; MDM Engineering supplies a missing shared primitive. Validate cycles, competing parents and unresolved endpoints where applicable. |
| 7. Publish for consumers | Select a mastered view and approved operational or analytical consumers, with provenance and recovery requirements. | MDM owns committed masters; the actual reader/destination owns delivery. Prove consumer readback. Do not promise source-system write-back or a generic API that has not been implemented and qualified. |

The table is a planning sequence with feedback: profiling informs domain design
before loading, and relationship semantics are agreed before rule activation.
It does not authorize loading raw records into MDM merely to discover them.

## One record's merging journey

1. **Retain and stage:** preserve captured evidence, source key, version and
   effective time. Acquisition and configured processing are separate actions.
2. **Map:** a Dataset Contract maps the source record into its accepted kind,
   identifiers, fields and relationship assertions; lookup references retain
   their separate role.
3. **Check and standardize:** run configured fixes and input checks before
   merging. Interpret codes against the approved reference version; preserve
   original evidence and report rejected or set-aside outcomes.
4. **Resolve identity:** use the kind's Identifier Contracts and approved
   matching rules. Keep record-to-master binding, permission to consolidate
   existing masters, and per-field survivorship as three separate decisions.
5. **Handle exceptions:** retain ambiguous/conflicting evidence for stewardship;
   creation, waiting and review follow policy. Apply an authorized resolution
   through supported application commands, with an attributable decision.
6. **Consolidate and explain:** the Merge Stage commits affected identities,
   source bindings, winning field values, history and reviews atomically. A
   linked analytical view retains source contributions and provenance; it does
   not require a second merge engine or changing the source application.
7. **Expose and verify:** readers consume committed changes from their own
   checkpoints. Verify the actual destination and recovery behavior. This
   platform's current reader contract is not a universal outbound push service.

See [MASTERING-STANDARD.md](MASTERING-STANDARD.md) for matching order, outcome
semantics, conflict handling and proof. Use [Refining rules](REFINING-RULES.md)
to change supported mappings, checks, matching or survivorship; preserve its
measurement, Mapping Document, testing and approval/activation requirements.

## Domains, transactions and reference data

**Master data** describes subjects with identity and lifecycle; **transactions**
record events about them. A slowly changing column or a table key alone does
not make a part master data. Classify each part from evidence.

**Multi-domain MDM** uses one configured engine across accepted kinds, with
distinct identity contracts and governed relationships between them. A
business process may use several kinds without merging unlike subjects into
one identity. A domain example is not authorization to add or activate a kind.

**Reference data** gives values their shared meaning through versioned code
sets, labels, definitions, valid dates, hierarchies and crosswalks. This platform
keeps it separately in RDM. Authorized owners draft, approve and publish new
versions; consumers pin the version they interpret. A code hierarchy in RDM
and a hierarchy of master entities in MDM are different structures.

## Examples

- Customer: a person or organization and its addresses; a purchase is a
  transaction. Product: an item and its governed structure; an order line is
  a transaction. Price classification depends on its grain and time model.
- Location: a site, building or room. Supplier/partner: a subject's business
  role, potentially a profile on an existing organization rather than a new kind.
- Asset or industry-specific subject: equipment, a patient or a member may
  need identity; a procedure performed or an insurance claim is an event.
- Similar invented names such as “Example Works Inc.” and “Example Works Co.”
  are candidates for investigation, not permission to merge. Conflicting
  authoritative identifiers or ambiguous evidence keep the decision unresolved.
