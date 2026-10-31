# Build a business catalog from the configured model

Use this procedure for catalog creation, recovery, business naming or publication
covering all entities and pipelines. Publish metadata only. Source records, job
execution, schedules and activation retain their own authorization.

Use service APIs and CLI tools only. Never use computer use, browser automation
or GUI interaction on this project.

## Discover meaning; do not maintain rename lists

Apply one source-neutral method to the whole selected rules root:

1. Discover entity kinds from the configured mastering model, policies and pinned
   relationship endpoints. Distinguish declared kinds from kinds with qualified
   operational mappings. Never enumerate entity or provider names in code.
2. Read each dataset's business definition, grain, record/publication keys,
   field definitions, lineage, master links and source-owned comments. Use the
   profiling findings and Dataset Contracts together; a storage path is not a
   business definition.
3. Infer the business subject and the role of each field from that evidence.
   Produce an understandable asset name, concise definition, domain association
   and glossary concept, with its configuration reference. Reuse existing terms
   when the meaning agrees. A shared spelling alone does not establish a shared
   meaning; different contexts may need different definitions.
4. When evidence is ambiguous, record a proposed interpretation and the precise
   uncertainty for review. Do not invent a meaning, owner, approval or identifier.
   Route missing business definitions to data-profiling/data-onboarding; changes
   to existing definitions go through refining-rules.
5. Persist reviewed meaning in the owning configuration. Generate presentation
   from that metadata and preserve its provenance. Do not fix an example with a
   source-specific branch, an ad hoc rename dictionary or a maintained list of
   entities. Correct the definition or generic derivation and regenerate all
   affected metadata, rather than editing the catalog as a second authority.

Display names must explain the business data. Preserve technical names/FQNs as
identities and lineage references, not as the only explanation. A column name
without its subject, grain and role is insufficient. Title-casing an internal
name is not semantic enrichment.

## Required business and technical coverage

| Object | Completion evidence |
|---|---|
| Entity domain | One native domain for every declared entity kind; distinguish definition-only kinds from operationally qualified ones |
| Business glossary | One glossary per entity domain, plus the shared glossary, projected from `CONTEXT.md` as `skills/data-catalog/references/OPENMETADATA.md` describes. Suggested, not approved |
| Business terms | Definitions and asset/column associations derived from the model and contracts; actual review status recorded |
| Datasets and fields | Clear business names, definitions, grain, provenance, master links and system-of-record boundaries |
| Pipelines | Every source and standalone target, its purpose, declared tasks, operations and dependencies; definitions do not imply enabled execution |
| Relationships | Pinned types, capacities, endpoint kinds and declared source lineage |
| Data quality | Named native test cases for configured checks, preserving semantics and failure action; corrections and proposals remain distinct |
| Mapping Documents | All configured sources, kinds, standalone pipelines and pinned relationship definitions; steward Notes preserved |
| Ownership | Existing authorized business owners where specified; otherwise an explicit unassigned responsibility, never the ingestion bot as a fabricated business owner |
| Data product | A configured package with a purpose and selected assets. Fundamental analytics is that package: three silver tables of filed figures, line items and measures. Create no native product until the rules name it. The test is in `skills/data-catalog/references/MODEL.md` |
| Classification | Data class from the data-modeling skill, one processing-layer tag per catalog-plan database, and the built-in certification: Gold on the master store, Silver on the prepared store. A proposed prepared-store table is Silver and has no data class. A source dataset has a layer and no data class |
| Domain relationship | One pinned relationship type from `mdm-relationship-types`. The asset sits on every endpoint domain. A capacity stays on its type. Not a `relatedTo` edge. The test is in `skills/data-catalog/references/OPENMETADATA.md` |

Include registered Silver/RDM metadata. Label profiling proposals as proposed;
never present them as existing registered tables or approved code sets. Do not
publish source samples or personal values in descriptions, terms or evidence.

Inventory first, then use the existing commands:

```bash
edgar-warehouse rules mapdoc write --root <rules>
edgar-warehouse rules mapdoc check --root <rules>
edgar-warehouse rules catalog plan --root <rules>
```

Omit `--only` for platform-wide work. Source workbooks include targets and steps;
standalone pipelines have their own `MAPPING.xlsx`; `merge/relationships.xlsx`
contains pinned types and capacities. Check workbook cells against configuration.

**Capability gate:** inspect the actual plan and publisher. If any required
native object, semantic association or readback is absent, record a demonstrated
capability gap and route it to implementation. The established technical plan,
publish and check commands do not assign domains, glossaries or native quality
cases. Domain type, multi-domain membership and MDM, RDM and silver layer
placement for the master-data subjects, and the glossary and classification
projection, are settled in `skills/data-catalog/references/OPENMETADATA.md`.
Follow that mapping on the API. Do not treat a green `rules catalog publish` as proof those links
exist, and do not invent a CLI flag to bridge the gap.

## Quality definitions are not execution results

Read configured checks from Dataset Contracts' quality configuration and
registered Silver specs. Preserve each check's meaning, inputs, parameters,
failure action, version and rules reference in its native test case. These
checks execute in their existing engine; an external test definition must not
pretend to be a runnable native SQL test or silently substitute another test.

- A fix changes a value; it is correction metadata, not a successful test.
- Profiling findings include proposals and historical measurements. They are
  not additional configured checks or current test results.
- Publish definitions without pass/fail counts, success statuses or fabricated
  execution dates. Result publication requires genuine corresponding execution
  evidence and is a separate capability and authorization boundary.
- Do not approve glossary wording or quality rules for a steward. Read actual
  review state; a populated catalog is not approval or activation.

The native API objects are domains, glossaries, glossary terms, quality test
definitions, logical test suites and test cases. Verify their supported schema
against the pinned server before implementation; never guess a payload.

## Restore the local catalog

Use the existing Docker context and documented named volumes:

```bash
docker compose -f infra/openmetadata/docker-compose.yml up -d
```

Check Docker first. If unreachable, recover through an approved API/CLI lifecycle
or report the exact blocker; do not launch or operate a GUI. Preserve other users'
containers and existing volumes. A cold start may take 10–20 minutes. The compose
file accepts `CATALOG_SERVER_HEAP_OPTS` and `CATALOG_SEARCH_HEAP_OPTS`; size them
against available memory and running stores.

Verify the running version through the API. Use an existing bot authorized for
the intended metadata operations; authentication alone does not prove authority.
Supply `OPENMETADATA_URL` and `OPENMETADATA_TOKEN` privately. Never print them,
commit them, or broaden permissions to hide a failed authorization check.

## Test first, reset the approved scope, then deploy

Before first deployment or a publisher change, qualify the pinned real API using
invented metadata in a separate task-owned namespace. Test all required object
types and associations, representative descriptions, real drift detection and
repair, stale cleanup, unrelated-object preservation and unchanged repeat.
Mocks and publish counts do not replace this proof.

The existing Python publishing API is
`edgar_warehouse.rules.catalog.publish(plan, call)` and its readback is
`verify(plan, call)`, with `call = connect(url, token)`. Use the actual supported
plan shape, not invented extension keys. Keep credentials outside the plan.

When the operator requests a reset, settle the target first. Reset only the
explicitly authorized metadata and synthetic assets. Preserve accounts, volumes,
shared stores, captures and business records. Verify the scope is empty before
deployment and retain a separate reset receipt.

For an authorized whole-service reset, process pipeline services then database
services using their documented API:

1. `GET /api/v1/services/<type>/name/<exact-owned-name>`; verify both the name
   and fully qualified name against the approved inventory.
2. `DELETE /api/v1/services/<type>/<returned-id>?recursive=true&hardDelete=true`.
3. Repeat the GET and require 404; record removed and remaining counts.

Domains, glossaries, terms and quality objects have independent/global scopes.
Do not assume service deletion removes them. Track only task-owned objects,
remove their references in dependency order, and preserve shared governance and
foreign test cases. Never recursively delete global definitions to bypass a
foreign dependency. A broad prefix is not proof of reset ownership.

After the implementation PR is merged, publish the selected committed rules:

```bash
edgar-warehouse rules catalog publish --root <rules>
edgar-warehouse rules catalog check --root <rules>
```

Verify business and technical coverage separately through the API. A green
technical check remains partial when it does not cover the required native
business objects. Read back display names, meanings, domain links, glossary
associations, quality definitions, tasks and lineage. Repeat publication and
readback; unchanged metadata must retain its versions.

Native bot PUTs can preserve descriptions; reconcile only owned metadata after
identity checks. Request pipeline tasks explicitly on readback. Markdown fields
may be HTML-escaped in transport: qualify exact one-level decoding, including
literal entity text and genuine negative cases. Do not strip meaningful text or
normalize identifiers, hashes or rule parameters to make a check pass.

Report counts and outcomes per object type, configuration digest and tested code
revision. Name missing owners, unreviewed definitions and unsupported publication
or verification paths. A technically populated service with no domains,
glossaries or meaningful labels is an incomplete business catalog.
