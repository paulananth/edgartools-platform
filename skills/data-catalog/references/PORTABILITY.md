# Replace the catalog or the renderer without redefining the data

Keep business meaning and logical identities in the owning configuration. Use
the existing definitions to produce a reviewable destination-neutral inventory
and typed relationships; do not build another metadata database as a prerequisite.
The catalog and independent visualization consume the same meaning. Neither
one is the sole place where a glossary definition or lineage transformation lives.

Preserve these in a portable inventory/export:

- logical key, object type, display name, definition, configuration provenance;
- subject-domain membership and independent processing-layer classification;
- technical containment, field identity/grain and glossary associations;
- pipeline/stage dependency, input/output mapping and transformation meaning;
- separate labeled control interactions, matching rules and quality definitions;
- actual responsibility, review/proposal state and qualified execution-evidence
  references where present, without fabricated approvals or results.

Record native destination identity as a mapping from the logical key, alongside
destination type/version and ownership scope. A renamed native FQN or a new
vendor must not silently create a different logical subject. One shared step
keeps one logical identity even when several pipelines reference it.

If a target lacks a native concept, identify the precise gap and propose an
explicit representation or companion view. A description-only fallback is
not equivalent to a searchable native association or traversable lineage edge.
Do not silently flatten typed links, lose field detail or infer relationships
from similar display names.

## Destination differences to verify

| Destination | Documented distinction | Qualification boundary |
|---|---|---|
| OpenMetadata | Domains and vocabulary coexist with service-based technical containment; asset lineage edges can reference a pipeline. | Use the pinned adapter reference and actual API readback. Native control-lane presentation remains a separate question. |
| Alation | A DataFlow is a process connecting source and target objects. Unresolved lineage object keys may produce temporary objects. | Resolve object identities first and test against the selected instance's API/version. Do not claim a pipeline-task or domain mapping just because similarly named objects exist. |
| Collibra | Community contains typed domains; an asset belongs to one domain and has an asset type. Terms and technical objects connect through configured relation types. Business and technical lineage are different representations. | Map a logical subject to the approved operating model. A subject-domain membership may require relationships across native containers; do not duplicate physical assets to force a one-to-one mapping. |
| Independent renderer | Layout, expansion and control lanes are presentation capabilities. | Read the same logical inventory and preserve its typed links. Test overview → pipeline → stage → fields independently from native catalog readback. |

Alation and Collibra are researched mappings, not installed or live-tested
adapters. Do not provision them or claim compatibility without an approved
destination and a connected invented proof. Licensing and connector availability
are instance-specific; verify them before promising native lineage behavior.

## Qualification for another destination

Choose a small connected invented model from configuration. Publish its domain,
terms, classifications, technical objects and process/field links; read them
back and normalize only the documented vendor representations to the logical
model. Verify typed associations, identity uniqueness and direction, not display
counts alone. A deliberately wrong expected edge must fail. Repeat for stable
identities and validate exact test-owned cleanup. Rebuild a separate view from
the same inventory; compare the underlying objects/links rather than pixels.

Keep the old destination until the selected replacement's review and native
qualification pass. Export/import test evidence is distinct from live adapter
qualification. Catalog portability does not authorize a data migration or a
change to execution bookkeeping.

## Primary references

- [Alation lineage and DataFlows](https://developer.alation.com/dev/reference/lineage-overview)
- [Alation API overview](https://developer.alation.com/dev/docs/alation-api-overview)
- [Collibra operating model](https://productresources.collibra.com/docs/collibra/latest/Content/to_operating-model.htm)
- [Collibra business glossary](https://productresources.collibra.com/docs/collibra/latest/Content/BusinessGlossary/to_business-glossary.htm)
- [Collibra lineage distinctions](https://productresources.collibra.com/docs/collibra/latest/Content/CollibraDataLineage/co_collibra-data-lineage.htm)
