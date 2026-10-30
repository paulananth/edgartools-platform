# Connected metadata qualification

The skill was written after the connected native API proof passed. Scope was
invented metadata on the existing local OpenMetadata 2.0.2 server, using its
existing authorized bot. No provider calls, source records, source execution,
new accounts, grants or infrastructure were involved.

## Native behavior

The final proof created and removed 14 exact test-owned objects. It read back:

- 2 table-to-domain assignments and 2 data-product memberships;
- 1 glossary parent/child relationship;
- 2 column glossary annotations and 2 column classification annotations,
  retaining their supplied Manual/Suggested label properties;
- 1 task dependency and 1 field-lineage edge associated with its pipeline;
- unchanged identities and versions after repeating every object publication;
- rejection of a deliberately incorrect expected transformation.

Cleanup first removed the exact lineage edge and read back its absence, then
used exact created IDs/FQNs in reverse dependency order, non-recursively.
All 14 objects and the 1 edge were removed; zero test-owned objects or edges
remained. Proof and cleanup have separate outcomes; overall pass requires both.
No quality results were
created. Counts/outcomes are in native-receipt.json. This does not claim that
native quality cases, a layer-browsing UI, separate control lanes or another
vendor were qualified by this proof.

The first two readbacks failed correctly: column annotations appeared empty
when only `tags` was requested. Inspection of the pinned TableRepository showed
that populating column tags requires `columns` and `tags`. The corrected request
read back both native label types and their exact Suggested states. Assertions
were retained; no approval state or annotation was fabricated.

Reproduce the bounded native test with explicit private paths:

```bash
uv run --no-project .planning/workstreams/portable-data-catalog-skill/qualify.py \
  --credentials-file <private-catalog-worker-json> \
  --evidence-dir <private-evidence-directory>
```

The worker JSON supplies OPENMETADATA_URL and OPENMETADATA_TOKEN. No value is
printed. It is not an adapter installer or production publisher. Interrupted
qualification requires reviewing its private ownership ledger and remaining-object
receipt and reconciling any in-flight request before another run. No recursive
cleanup command is provided. Recovery is operator-led; the script refuses a new
run if its existing ledger does not record completed cleanup, preserving that
ledger rather than overwriting it with a new namespace.

## Skill behavior

An independent low-reasoning reviewer used the skill against a request to treat
the physical table tree as business domains, repeat task names as control labels,
and invent passing quality results. It corrected all three, preserved the
domain/layer distinction, required genuine result evidence, and kept the future
catalog and separate renderer unqualified pending their own test. Its one
clarification gap was addressed: missing domainType policy now explicitly
requires an operator mapping decision before real publication.

Its final review caught separate lineage-edge cleanup accounting and overall
pass-state gaps. Both were fixed before the final native rerun. The final receipt
records successful proof and cleanup independently, with zero owned objects and
edges remaining.

## Standards

Fresh dedicated branch/worktree; source-neutral skill; private credentials;
metadata-only API proof; no computer use or live source data. The skill creator
validator and 94 genericity/path checks passed after initial writing. The
complete skill directory is included by the existing data-skill bundle rule.
The built wheel contained all 5 skill files byte-for-byte; the actual bundle
installer copied the skill and references into both supported runtime folders
under a temporary home. Actual home was untouched. This qualifies delivery of
the skill, not live adapter support.

## Spec

Business-domain-first browsing and a separate layer filter are the operator's
choices. One logical model serves the catalog and independent visualization.
OpenMetadata terminology is isolated in a versioned reference. Alation and
Collibra are researched destinations, not tested adapters. Existing engine
capability gaps remain explicit; no new runtime migration is claimed.

## GoF

Existing catalog projection/API boundaries are adequate. This change adds a
skill and a bounded qualification script; plain functions suffice. No production
code refactor or vendor framework is justified to document the portable model.
