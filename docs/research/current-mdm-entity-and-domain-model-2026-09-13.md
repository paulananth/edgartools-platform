# Current MDM Entity and Domain Model

**Question:** Does the current MDM use one legal-organization identity with multiple roles, or separate Company, Adviser, Person, Security, Fund, and Audit Firm records?

**Evidence base:** `origin/main` at commit `2a66c926fee24562f916902b2850a9a9bc51e97a` (2026-09-13). This report uses the committed application schema, migrations, write paths, read/export/graph consumers, tests, and git history. It does not infer the production schema from planning documents.

## Direct answer

The current model is a **typed registry plus separate domain tables**:

1. `mdm_entity` supplies a shared registry key, but each registry row has exactly one scalar `entity_type` value. The allowed values are `company`, `adviser`, `person`, `security`, `fund`, and `audit_firm` (`edgar_warehouse/mdm/database.py:159-195`; `edgar_warehouse/mdm/migrations/005_fundamentals_relationships.sql:15-36`).
2. Each domain has its own table and uses `entity_id` as both its primary key and a foreign key to `mdm_entity`: `mdm_company`, `mdm_adviser`, `mdm_person`, `mdm_security`, `mdm_fund`, and `mdm_audit_firm` (`edgar_warehouse/mdm/database.py:230-397`).
3. A real organization that appears as both a Company and an Adviser is represented today by **two MDM entity IDs**, one per domain. `mdm_adviser.linked_company_entity_id` links the Adviser record to the Company record, and the pipeline publishes the link as `IS_ENTITY_OF` (`edgar_warehouse/mdm/adv_bulk.py:259-315`; `edgar_warehouse/mdm/migrations/002_seed_data.sql:260-264,549-574`; `edgar_warehouse/mdm/pipeline.py:2269-2286,4719-4725`).
4. An individual Adviser and a Person are also separate identities. Matching CIKs produce `IS_PERSON_OF`; the Adviser ID is not reused as the Person ID (`edgar_warehouse/mdm/migrations/002_seed_data.sql:275-279`; `edgar_warehouse/mdm/pipeline.py:2420-2437,4727-4735`; `tests/mdm/test_pipeline_relationships.py:273-297,374-381`).
5. There is no role-assignment table, role collection, or multi-role projection in the current schema. Source references and staged attributes attach to one typed `mdm_entity`; resolvers are instantiated with one `entity_type` and create a registry row with that type (`edgar_warehouse/mdm/resolvers/base.py:88-129`).

Therefore, **one `entity_id` spanning multiple domain tables is not a valid current-domain representation**. The database foreign keys do not prevent the same UUID from being inserted into more than one domain table, but that would be an unenforced and unsupported state:

- `mdm_entity.entity_type` can name only one domain (`edgar_warehouse/mdm/database.py:159-195`).
- API search and stewardship choose exactly one domain model from that one type (`edgar_warehouse/mdm/api/routers/entities.py:40-81`; `edgar_warehouse/mdm/api/routers/stewardship.py:77-101`).
- Export groups by the one type and selects exactly one domain table (`edgar_warehouse/mdm/export.py:309-349,510-529`).
- Graph publication type-gates each domain join with `E.ENTITY_TYPE = '<type>'`, so a second domain row using the same ID would be ignored (`edgar_warehouse/mdm/snowflake_graph.py:1337-1394`).

## Physical model by domain

| Domain | Registry type | Domain table | Domain identity or uniqueness currently used | Link to another domain |
| --- | --- | --- | --- | --- |
| Company | `company` | `mdm_company` | `entity_id` PK; `cik` unique | `parent_company_entity_id` points to an `mdm_entity` |
| Adviser | `adviser` | `mdm_adviser` | `entity_id` PK; `crd_number` unique; `cik` is not unique | `linked_company_entity_id` points to the corresponding Company identity |
| Person | `person` | `mdm_person` | `entity_id` PK; `owner_cik` is not unique | `IS_PERSON_OF`, `IS_INSIDER`, and other relationships connect distinct identities |
| Security | `security` | `mdm_security` | `entity_id` PK; current resolver deduplicates by issuer plus normalized title; `cusip` and `isin` are not unique constraints | `issuer_entity_id` points to the issuer identity |
| Fund | `fund` | `mdm_fund` | `entity_id` PK; `private_fund_id` unique; fallback identity uses adviser plus name/source identity | `adviser_entity_id` points to the Adviser identity |
| Audit Firm | `audit_firm` | `mdm_audit_firm` | `entity_id` PK; `pcaob_firm_id` unique in PostgreSQL migration | `AUDITED_BY` connects Company to Audit Firm |

Schema evidence: `edgar_warehouse/mdm/migrations/001_initial_schema.sql:25-120`; audit-firm extension: `edgar_warehouse/mdm/migrations/005_fundamentals_relationships.sql:40-62`; ORM mirror: `edgar_warehouse/mdm/database.py:234-397`.

The cross-domain foreign keys reference only `mdm_entity(entity_id)`. PostgreSQL does not constrain, for example, `linked_company_entity_id` to an entity whose type is `company`, or `adviser_entity_id` to type `adviser` (`edgar_warehouse/mdm/migrations/001_initial_schema.sql:52-120`). Relationship-type metadata declares expected endpoint types, but relationship-instance foreign keys also reference the untyped registry key (`edgar_warehouse/mdm/migrations/001_initial_schema.sql:231-289`). These are application invariants, not fully enforced database invariants.

## How Company and Adviser linkage works

The Adviser bulk resolver builds a map from `mdm_company.cik` to Company `entity_id`. It independently creates or updates an Adviser `mdm_entity` with `entity_type='adviser'`, then stores the matched Company ID in `mdm_adviser.linked_company_entity_id` (`edgar_warehouse/mdm/adv_bulk.py:259-315`).

The relationship registry defines `IS_ENTITY_OF` as Adviser to Company and describes it as “the same legal entity as a registered company.” The derivation reads `(adviser.entity_id, adviser.linked_company_entity_id)` and writes the edge; it does not merge the two entities (`edgar_warehouse/mdm/migrations/002_seed_data.sql:260-264`; `edgar_warehouse/mdm/pipeline.py:2269-2286,4719-4725`). The API follows that foreign key to return the related Company (`edgar_warehouse/mdm/api/routers/advisers.py:27-44`; `edgar_warehouse/mdm/api/routers/companies.py:70-76`).

The tests make the intended shape explicit: a firm-style Adviser and its linked Company are created with different IDs, while an individual Adviser and its Person are also created with different IDs and linked separately (`tests/mdm/test_pipeline_relationships.py:257-332,366-381`).

## Write-path invariants

- Each ordinary resolver has one fixed `entity_type`. `BaseResolver._create_entity()` writes that type, source references attach to the resulting ID, and survivorship rules are selected for that same type (`edgar_warehouse/mdm/resolvers/base.py:88-129,171-194`).
- Company matching searches `MdmCompany` only, Person matching searches `MdmPerson` only, and Security matching searches `MdmSecurity` only (`edgar_warehouse/mdm/resolvers/company.py:172-188`; `edgar_warehouse/mdm/resolvers/person.py:145-165`; `edgar_warehouse/mdm/resolvers/security.py:183-203`). Cross-domain records are not candidates in these resolvers.
- Adviser and Fund bulk resolution independently inserts one typed `MdmEntity` row followed by the corresponding domain row (`edgar_warehouse/mdm/adv_bulk.py:276-349,441-520`).
- Audit Firms are separate typed entities. The seed path creates an `audit_firm` registry row and a matching `mdm_audit_firm` row (`edgar_warehouse/mdm/seed/audit_firms.py:108-168`).

There is one important missing guard: manual merge redirects source references and tombstones the discarded registry entity without checking that `keep` and `discard` have the same `entity_type` (`edgar_warehouse/mdm/stewardship.py:130-179`). That absence does not establish multi-role semantics; it exposes a cross-type corruption risk if callers supply IDs from different domains.

## Read, export, and graph consequences

The current consumers depend on one-type-per-entity:

- Entity API filtering maps one `entity_type` to one domain class (`edgar_warehouse/mdm/api/routers/entities.py:40-81`).
- Manual field override selects one domain row from `mdm_entity.entity_type` (`edgar_warehouse/mdm/api/routers/stewardship.py:77-101`).
- MDM export has independent Company, Adviser, Person, Security, and Fund targets, and groups pending changes by their single `entity_type` (`edgar_warehouse/mdm/export.py:23-29,309-349`).
- Snowflake provisions five separate Golden Record export tables keyed by `entity_id` (`infra/snowflake/sql/bootstrap/07_mdm_export_targets.sql:1-32,83-166`).
- Graph nodes use the registry ID as `NODEID`, take one label from the entity type registry, and join only the matching domain table (`edgar_warehouse/mdm/snowflake_graph.py:1319-1394`). Cross-domain sameness is expressed as an edge, not multiple labels on one node.

### Audit Firm is only partially integrated

`audit_firm` exists in PostgreSQL and the graph’s allowed entity types, but it is absent from `DOMAIN_TO_TABLE`, the five Snowflake Golden Record targets, the mirror generator’s `MDM_TABLES`, dashboard domain maps, and stewardship patch map (`edgar_warehouse/mdm/export.py:23-29`; `infra/snowflake/sql/bootstrap/07_mdm_export_targets.sql:1-16,83-166`; `edgar_warehouse/mdm/migrations/runtime.py:46-66`; `edgar_warehouse/mdm/dashboard_readonly.py:32-46`; `edgar_warehouse/mdm/api/routers/stewardship.py:89-98`).

The graph can create a generic Audit Firm node from `MDM_ENTITY`, but its property query has no `MDM_AUDIT_FIRM` join (`edgar_warehouse/mdm/snowflake_graph.py:1337-1394`). This is a present integration gap, not evidence of a generic multi-role model.

## History

- Commit `bf8a8431f2b61b678562fb0420431ec59808db72` introduced the initial registry plus five separate domain tables on 2026-04-24.
- Commit `536d970acf0be2a1d2d893cfa3ac1ccb193711ee` added the matching SQLAlchemy model layer on 2026-04-24.
- Commit `947c0661b8ef852a977bf31610d3eb7c67ff69f1` added Audit Firm as a sixth entity type, its separate domain table, and typed relationships on 2026-05-29.
- Commit `84808341ac9c3c85e9c141997e4a97e1b9103a85` introduced the current Adviser/Fund bulk projection path on 2026-07-24. Later fixes changed batching and deduplication, not the separate-domain identity shape (`877313ad2bb1632db081bd2fbdf315047a616e9e`, `ee62a968c7addb279aa4f8b2b513d126f3de0525`, `e6fc0626994d8fdd972c6a9efeee72b1c32e25e6`).

The history shows extension by adding another typed domain table and relationships, not by changing `mdm_entity` into a multi-role legal-party record.

## Wayfinder recommendation

Do not make the previously proposed “one real legal organization has one `entity_id` with multiple governed roles” assumption part of the GLEIF enrichment design. It is not the current model.

For the current Wayfinder map:

1. Preserve the existing domain-specific identities and domain tables.
2. Enrich Company through `mdm_company`; enrich Adviser through `mdm_adviser`; keep Person, Fund, Security, and Audit Firm separate.
3. When external evidence proves that a Company and Adviser describe the same legal entity, retain both IDs and govern the cross-domain `IS_ENTITY_OF` link. Use `IS_PERSON_OF` for an individual Adviser-to-Person equivalence.
4. Treat a unified Legal Organization identity with multiple roles as a separate, large data-model migration decision. It would require a role-assignment schema plus changes to resolvers, survivorship, merge safety, APIs, export tables, graph labels, checkpoints, and migrations.
5. Before Release 1 can claim all mandatory master domains, specify physical domain tables and consumers for any new domains that origin/main does not support, and close the existing Audit Firm export/read gap.

This recommendation preserves current behavior while allowing GLEIF evidence to augment each supported domain without silently redefining identity across the whole platform.
