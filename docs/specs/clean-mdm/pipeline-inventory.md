# Current pipeline inventory and target routing

Status: inspected code at `b1babd8bbd0e04044fcacbbab822d480c97c01bc`.
Paths below are under `edgar_warehouse/` unless stated otherwise. Line numbers
refer to that commit. This is code evidence, not a live production audit.

## Existing entry points and stage order

Keep CLI mastering, relationship derivation/publication, reconciliation and
repair entry points. `mdm/pipeline.py:2898` currently starts five entity phases
concurrently, then derives relationships and requests publication. Company →
Person → profiles → supported issuers/Security/Fund is an explicit target
dependency correction, not an already implemented sequential behavior.
Parallelism can remain only between dependency-independent bounded batches.

## Source-to-consumer matrix

| Path and evidence | Inputs | Current identity / role / relationship effects | Target routing and publication |
| --- | --- | --- | --- |
| Company — `mdm/pipeline.py:784`, `mdm/resolvers/company.py:70` | `sec_company`, tickers, Bookkeeping tracking status | CIK matching, Company fields, source refs, survivorship and change log; excludes individual reporting owners | Company assertions → Merge Stage; explicit issuer eligibility, namespaced source fields; versioned identity/field-provenance export and graph |
| ADV Adviser — `mdm/adv_bulk.py:195` | Latest `sec_adv_filing` per CRD or accession; `sec_adv_office` | Separate Adviser ID linked to Company by CIK; direct bulk non-null overwrites at line 308 bypass shared survivorship | Classify holder as Company/Person, then attach governed registration profile; no new role identity; expose profile registration history |
| ADV Fund — `mdm/adv_bulk.py:353` | `sec_adv_private_fund`; PFID or accession/index; adviser context | Separate Fund ID; source occurrence key is accession/index (line 425); name/adviser fallback dedup | Legal-form and structure evidence selects Company Fund profile or Fund Structure; preserve every occurrence; publish profile and management links |
| Ownership Person — `mdm/pipeline.py:1376`, `mdm/resolvers/person.py:66` | Reporting owners and filing issuer context | Person matching by CIK then fuzzy fallback; name/primary-role fields; `IS_INSIDER` at line 1740 | Person assertions with source-specific capacities; contextual role facts do not create Adviser registration |
| Ownership Security and positions — `mdm/pipeline.py:1220`, `:1940`, `:2141`, `:2800` | Derivative/non-derivative transactions joined to owner and filing | Security by issuer/title; `HOLDS`, `COMPANY_HOLDS`, Company-only `ISSUED_BY` | Separate Security identity; typed issuer contract; distinguish positions, transactions, dates, units and reporting capacities |
| 13F — `mdm/pipeline.py:4413`, `:3367`, `:3598` | `sec_thirteenf_holding`, filings and amendments | CUSIP Security stubs, `INSTITUTIONAL_HOLDS`; manager CIK becomes Adviser with `adviser_type=13f_manager` | Submit manager/instrument evidence to Merge Stage; legal kind and regulated Adviser eligibility need independent proof; retain 13F reported-manager semantics |
| Proxy/officer — `mdm/pipeline.py:3743`, `:3520` | `sec_executive_record`, `sec_employment_event` | Person lookup/stub creation inside derivation; dated `EMPLOYED_BY`, compensation/role properties | Identity first, then reported employment; no direct stub master writes; provenance includes event and filing dates |
| Audit — `mdm/pipeline.py:4070`, `:3426`; `mdm/seed/audit_firms.py:108` | `sec_auditor_report_evidence`, fallback `sec_accounting_flag`, PCAOB/name evidence | Separate Audit Firm ID; dated `AUDITED_BY`; identifier then exact case-insensitive name lookup | Company identity plus governed Audit Firm profile; preserve dated engagements and ambiguous firm-name review |
| Parent hierarchy — `mdm/pipeline.py:2333`, `:2419` | `sec_subsidiary_evidence` | Company stubs and `HAS_PARENT_COMPANY` with parent scope, jurisdiction and reported date | Preserve source assertion; split ownership/accounting semantics and reported/calculated ultimate parents; validate scoped temporal cycles |
| Adviser associations — `mdm/pipeline.py:2314`, `:2465` | Linked Company/Person fields | `IS_ENTITY_OF`, `IS_PERSON_OF` join separate domain IDs | Same-identity profile membership; genuine employment/association remains a separately evidenced relationship |
| Shared relationships — `mdm/graph.py:76`, `:521`, `:632`; `mdm/relationship_checkpoint.py` | Eleven registered types, derivation candidates and temporal evidence | Versioning, supersession, quarantine, incremental checkpoints; some callers also create identities | Reuse temporal concepts; all identity creation and relationship effects use the same journal/transaction; checkpoint includes policy and generation |
| Resolution backstop — `mdm/reconciliation_backstop.py:36`, `mdm/resolvers/base.py:235` | Existing source assignments and complete tracked universe under lease | `run_all(reconciliation_pass=True)` re-evaluates ordinary resolvers; ADV bulk lacks this flag | Explicit pinned replay through Merge Stage for every adapter, with bounded progress and policy version |
| Graph reconciliation — `mdm/cli.py:514`, `:547` | MDM and published graph | `mdm reconcile` verifies graph; it is not the resolution backstop | Preserve distinction and verify exact new identity/profile/edge contract |
| Stewardship — `mdm/stewardship.py:54`, `:130`; `mdm/api/routers/stewardship.py:78` | Match review, quarantine, manual merge and field patches | Merge only moves source refs/tombstones loser; field overrides directly update domain tables | Evidence-bound decisions through Merge Stage; kind/identifier guard, affected closure, reversible merge and compensating publication |
| Export — `mdm/export.py:294`, `:375`, `:396` | Pending change log, entity/domain rows, relationship versions | Five domain exports plus mirrors; separate `exported_at` and `graph_synced_at` markers | Versioned identities/profiles/identifiers/assertions/fields/relationships/aliases; independent verified consumer receipts |
| Graph — `mdm/snowflake_graph.py:1374`, `:1494`, `:2112`, `:2148`, `:2284` | Snowflake MDM mirrors and relationship lineage | Type-gated domain joins, remapped merged IDs, exact parity and endpoint checks | Shared identity nodes and explicit profiles; reported/derived edge distinction, provenance references, exact generation parity |
| API — `mdm/api/schemas/entities.py:14`; `mdm/api/routers/entities.py:33`, `companies.py:71`, `funds.py:23` | Entity/domain projections, source endpoints, attribute-stage evidence | Separate Company/Adviser/Fund shapes; no versioned shared profile/winner-rule contract | Versioned shared identity response, profile histories, provenance and aliases; compatibility reads use a verified crosswalk |

## Reusable foundations and gaps

- `mdm/migrations/014_source_registry.sql:54` is acquisition-universe
  coverage, not the dataset/assertion registry proposed here.
- `015_source_evidence_conflict.sql:33` tracks immutable Bronze conflicts,
  not selected master-field disagreement.
- `mdm/survivorship.py:132`, `:172`, `:353` stages candidates and winners.
  Null/empty filtering and load-time tie-breaking do not satisfy the new
  correction, deletion and order-independent policy contract.
- `mdm/publication.py:59` can enqueue transactionally, but
  `mdm/pipeline.py:3116` requests publication after separately committed
  entity phases. Per-batch publication intent is necessary.
- Audit Firm is present in the identity model but absent from the five-domain
  export mapping. A shared profile redesign must close this consumer gap,
  not merely rename tables.

## Approved extensions and non-implementation

The [source evidence contract](source-evidence.md) maps all three GLEIF Golden
Copy record families and six independently checkpointed mappings. They remain
unimplemented in the inspected runtime. Existing ISIN columns and acquisition
registry machinery are not evidence of those adapters.

The prior Branch, Government Entity and International Organization decisions
are preserved as domain boundaries and reconciled in the new model. The new
Fund Structure and Market/Venue representation proposals are explicit policy
gates. Conditional providers keep their existing adoption/licensing gates.
