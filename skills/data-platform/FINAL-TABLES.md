# Final exposable tables

One repository configuration is the authority for which physical tables may
leave the processing stores. Both managed mirroring and AutoOntology consume
the same explicit list. OpenMetadata displays that decision; a catalog edit
does not authorize exposure or expand the list.

## Eligibility

Only final MDM master tables, final RDM master tables and final registered
silver tables may be selected. Layer membership, a data-class tag or a store
certification alone is insufficient. Identify the actual physical relation
and its consumer contract; a logical catalog asset is not proof that relation
exists. A table whose name includes master is not automatically eligible.
RDM's tables hold draft versions beside published ones, so none of them is final: its final output is `rdm.published_code`, written once when
a version is published (the published-only form of the `rdm.code_context` view, which a mirror cannot carry).

For every selected table, configuration must state its store connection key,
database/schema/table identity, final-output role and exposure eligibility.
Derive that eligibility from approved requirements and the source-to-final
mapping, using [Data profiling](../data-profiling/SKILL.md#exposure-tags-follow-requirements-and-mappings)
evidence. Reference their versions and show which requirement each final table
and its mapped fields satisfy. A manual tag, layer name or inferred class
cannot replace that trace. Missing requirements, incomplete mappings or
unresolved sensitivity/quality decisions leave the table ineligible.
Data-profiling supplies the measured evidence; data-modeling defines the final
outputs and each output's current/history scope from requirements and mappings.
Include the exact exposure list in the existing requirements-and-mapping
approval, backed by the profiling report, before recording it in configuration.
There is no separate table-tagging approval round. Record the exact reviewed
requirements, mapping and list versions and operator words;
pending or declined entries cannot enter either consumer. Metadata publication
and billable mirror creation retain their separate gates.
Resolve those entries into exact physical table lists for both consumers.
Omission means ineligible. New tables remain ineligible until configured and
verified. Keep live addresses and credentials in private connection files.

Exclude source readings, stage/work tables, drafts, match candidates, rejected
records, migration metadata, checkpoints, queues, outboxes, leases and other
processing/control tables. Check table contents as well as names: if a
physical table mixes drafts or internal rows with final output, whole-table
mirroring does not satisfy this contract. Stop and resolve the final physical
output boundary; tags do not filter rows. Do not select unsupported views as
a managed-mirror workaround.

Exposure eligibility does not establish approval, readiness or activation.
Retain source qualification, primary-key/type checks and each consumer's
authorization and verification gates.

## Consumer enforcement

- **Managed mirrors:** pass the resolved list as `postgres_tables` and set
  `postgres_schemas` to NULL. A schema-wide mirror is outside this scope.
  Compare every mirrored table to the configured list; report missing and
  unexpected tables independently. Adding a table requires configuration and
  the normal add-table procedure; never silently widen a schema selection.
- **AutoOntology:** import and query only that same table list, using dedicated
  SELECT-only readers. Schema-wide SELECT and future-table grants do not
  enforce the list. Prove table-level read boundaries and exact imported
  identities, including absence of internal and stale assets, before ingestion,
  sampling, embeddings or semantic compilation. If upstream table filters are
  insufficient, qualify a restricted-reader path rather than importing broadly.
- **OpenMetadata:** project the configured eligibility as a classification tag,
  distinct from data class, layer, certification and glossary annotations.
  Read back exact tagged-table membership, including the absence of that tag on
  excluded tables. Preserve the rest of the catalog: internal metadata can
  remain documented without being exposed to mirroring or AutoOntology.

## Capability gate

The exposure scripts (manifest, OpenMetadata publication, AutoOntology connection, parity and
operations) are in [scripts/exposure/](scripts/exposure/README.md). They are unqualified: their open
findings are the connectivity tracker's tickets, and none runs against a live service until its
ticket closes.

These are operator requirements, not a claim of installed enforcement. Before
execution, verify that the configuration parser, table-list resolution, mirror
caller, reader grants, AutoOntology inventory check and catalog tag projection
all implement the contract. The existing source configuration and catalog sync
helpers select schemas; they are insufficient for this narrower table scope.
If a required capability is missing, report that gap and stop the affected
workflow. Do not invent a configuration field, CLI flag or tag name and treat
it as already supported. A skills-only update neither applies live tags nor
reconciles existing grants, mirrors or consumer state.
