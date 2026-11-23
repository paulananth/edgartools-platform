---
name: mdm-data-publication
description: Select and govern the master-data tables, views, APIs, reference values, and relationships exposed to consumers while keeping MDM internals private. Use when defining or reviewing MDM publication, managed database mirrors, Gold models, operational APIs, analytical views, reference data, or hierarchy exposure.
---

# MDM Data Publication

## Quick start

Publish curated, governed products with a declared consumer and purpose. Keep
hub internals private. A schema, table name, tag, successful load, or existing
database is not approval to expose its contents.

Maintain an explicit, versioned assignment for every physical source table and
published output. Do not use schema-wide fallbacks or wildcards. An absent,
pending, declined, or stale assignment is ineligible; an empty approved set
stays empty and blocks publication.

## Workflow

1. **Choose the consumer contract.** State whether the output supports
   operational use, analytical use, shared reference lookups, or relationship
   navigation. Name its consumer, purpose, freshness expectation, access class,
   and owner. Operational Golden Records and analytical linked views have
   different update and source-mutation semantics.
2. **Classify each output by its meaning and lifecycle.** Publish authoritative
   Golden Record representations, consolidated analytical views, published
   reference values, and governed hierarchy or relationship outputs. Keep raw
   staging, unresolved or pending stewardship work, match candidates and
   scores, system metadata and audit logs, and reference-data authoring/admin
   structures internal. When one physical table mixes these purposes, publish
   a curated projection that contains only approved consumer fields.
3. **Record exact assignments.** For each approved output, record the physical
   source database/schema/table, destination and object, business purpose,
   consumer, grain or identity, time scope, field classification, producer,
   and evidence for requirements, profiling, modeling, and approval. Keep
   output names distinct from physical source names. Never infer eligibility
   from a schema, name, catalog tag, or another table's approval.
4. **Verify the source evidence.** Read the actual source contract and profile
   the selected tables read-only. Verify existence, supported table shape,
   primary-key behavior, column types and precision, null/duplicate behavior,
   grain, lineage, and freshness. Identify sensitive fields and confirm the
   consumer's access rules. Stop if any required check or approval is missing;
   report the exact gap and its owner.
5. **Connect configuration to the destination.** Use the same approved
   assignment list to drive mirror membership and any other configured
   consumer. For a managed mirror, pass an explicit table list and verify
   returned membership after creation; do not select whole schemas as a
   shortcut. Treat mirror replication and Gold transformation as separate
   products. A table being mirrored does not by itself make it a Gold input.
6. **Model Gold at business grain.** When requirements call for Gold, configure
   entity dimensions and facts at their declared grains. Reuse conformed
   dimensions and verify joins preserve fact counts and relationships. Build
   only approved outputs; distinguish ordinary views from certified semantic
   views and do not claim certification from a successful build.
7. **Verify access and readback.** Confirm the consumer role can read the
   intended outputs and cannot read internal structures. Read back the
   destination's actual membership, object definitions, freshness, and
   representative behavior. A successful create or deploy command is not
   publication proof. Report configured, approved, activated, and verified
   states separately.
8. **Control changes.** A new table, field, consumer, destination, or purpose
   needs its own current assignment and evidence before it is exposed. Removing
   an assignment does not automatically authorize dropping a mirror or target;
   verify consumer impact and follow the destination's separate removal and
   deletion controls.

## Handoffs

- [Data Modeling](../data-modeling/SKILL.md) owns entity, domain, identity,
  relationship, and grain decisions.
- [Data Profiling](../data-profiling/SKILL.md) supplies evidence; it does not
  approve publication. [Data Governance](../data-governance/SKILL.md) owns
  governed lineage and approval evidence.
- The selected destination's skill owns implementation and native readback.

See [EXAMPLES.md](EXAMPLES.md) for an example assignment and exposure boundary.
