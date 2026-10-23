# MDM caller and routine inventory

Baseline: main `4b1bb68f`, merged from qualified PR #1148. This is a source and fresh-install catalog inventory, not full MySQL workflow qualification or a production-store audit.

## Measured baseline

| Measure | Count | Meaning |
|---|---:|---|
| Migration files | 27 | Registered installation/upgrade history |
| All migration source lines | 4,874 | Includes DDL, views, comments and superseded definitions |
| CREATE function declarations over history | 56 | Includes replaced definitions |
| Installed current function names | 36 | Fresh PostgreSQL 16 normal migration catalog matches the reconstructed list; no overloads |
| Latest source-definition lines for those functions | 1,130 | Includes storage enforcement; not a deletion estimate |

The last source definition for each installed name is counted from its CREATE declaration through its closing dollar quote. A later DROP removes it from the list. The normal owner migration was applied twice to a fresh disposable PostgreSQL 16 database: 36 catalog names match, second installation changes nothing. The disposable server stopped. Historical `match_proposal_snapshot` is already dropped by migration 020.

Active views, Python SQL, constraints and the skill-owned generated storage capabilities are additional code surfaces. They are not included in the 1,130 function-definition lines. The approximate “6,000 lines” is not an active business-logic deletion budget.

## Current caller operations

| Operation and current entry point | Remaining PostgreSQL coupling / integration gap | Next owning ticket |
|---|---|---|
| `clean/store.py:migrate`, `schema.py:configure_kinds`, policy/dataset registration | Normal owner migration refuses non-PostgreSQL; catalog/role/advisory-lock DDL and configured views remain native. Isolated typed registry helpers are not an owner migration. | Install governed MDM storage on both engines |
| `MergeStage.propose`; `binding.holders/propose/proposal_is_stale`; matching and correction | RecordReader transports current/candidate/member inputs, but proposal holders, publication floors and remaining correction queries still expect SQL connections. | Connect indexed records to shared matching and scope |
| `scope.py:identities/links/_chain/stored_links_and_reviews` | Scope, identity/member/link closure, retirements and hierarchy retrieval still use native tables, array casts and lookup functions. | Connect indexed records to shared matching and scope |
| `MergeStage._execute`; `assessment.record_in/load/supersede`; `Store.commit` | Advisory save lock, preview, current generation, durable assessments and normal save use PostgreSQL SQL/functions. Native prepared effects do not supply this complete transaction contract. | Commit the normal Merge Stage atomically |
| Current/history/detail reads, `context.py`, `clean/consumer.py` | Context uses native entity/search/cross-reference functions and views. Domain-shaped projection/history remains in native storage. | Connect master reads and operator commands |
| `silver_writer/writer.py:Ids` | Real master-ID lookup uses `stage_record`, `current_entity` and PostgreSQL casts. Callback link tests cannot qualify it on MySQL. | Connect master reads and operator commands |
| `clean/cli.py:counts/check_connectivity/force_publish` | Counts and forced publication still use the native schema/capability. | Connect master reads and operator commands / Connect worker authority and publication recovery |
| `workers/mdm_merge.py:_store`, `clean/execution.py`, `clean/run.py`, `Store.run_status/deliver_one` | Normal worker constructs PostgreSQL-only Store; destination guard and run/publication observations use PostgreSQL transactions and schema. | Connect worker authority and publication recovery |

Shared computation already exists in native identity replay, current-claim preparation, master preparation, relationship projection, record history/index preparation and matching comparison. Reuse those operations. Migrate transport and authority without creating a second merge algorithm.

## Installed routine dispositions

These are responsibility assignments, not approved DROP statements. Each retirement must account for Python callers, inter-routine calls, triggers/indexes/views and published SQL-reader interfaces. Static references below include source occurrences; they do not claim all external SQL clients have been audited.

### Shared preparation or display expressions

6 routines; 110 latest source lines. Next tickets: 03 / 04 / 05. Replace or compile from shared operations; retire stored copies only after equivalent caller behavior is proved.

| Routine | Latest definition | Lines | Python source references / internal caller |
|---|---|---:|---|
| `detail_rows` | [022_detail_version.sql:45](../../../edgar_warehouse/mdm/migrations/022_detail_version.sql#L45) | 7 | `record_detail_versions` |
| `entity_name` | [006_relationship_context.sql:12](../../../edgar_warehouse/mdm/migrations/006_relationship_context.sql#L12) | 8 | edgar_warehouse/context.py:301; `entity_search`; `relationship_chain` |
| `relationship_holds` | [006_relationship_context.sql:79](../../../edgar_warehouse/mdm/migrations/006_relationship_context.sql#L79) | 10 | edgar_warehouse/context.py:472; `relationship_chain` |
| `stage_claim` | [001_mdm.sql:1139](../../../edgar_warehouse/mdm/migrations/001_mdm.sql#L1139) | 8 | `stage_fold` |
| `stage_fold` | [023_stage_details.sql:6](../../../edgar_warehouse/mdm/migrations/023_stage_details.sql#L6) | 62 | `record_stage` |
| `stage_profile_key` | [001_mdm.sql:1210](../../../edgar_warehouse/mdm/migrations/001_mdm.sql#L1210) | 15 | `stage_fold` |
### Mixed preparation and durable writes

10 routines; 535 latest source lines. Next tickets: 04. Split preparation from atomic storage. Preserve revision ordering, binding checks, history intervals, detail/relationship history and publication.

| Routine | Latest definition | Lines | Python source references / internal caller |
|---|---|---:|---|
| `keep_detail_versions` | [022_detail_version.sql:99](../../../edgar_warehouse/mdm/migrations/022_detail_version.sql#L99) | 9 | SQL reader, trigger/index or stored capability dependency; preserve until its replacement ticket accounts for it. |
| `keep_relationship_version` | [010_relationship_version.sql:121](../../../edgar_warehouse/mdm/migrations/010_relationship_version.sql#L121) | 9 | SQL reader, trigger/index or stored capability dependency; preserve until its replacement ticket accounts for it. |
| `keep_stage` | [001_mdm.sql:807](../../../edgar_warehouse/mdm/migrations/001_mdm.sql#L807) | 62 | `write_batch` |
| `record_binding` | [001_mdm.sql:954](../../../edgar_warehouse/mdm/migrations/001_mdm.sql#L954) | 22 | `keep_stage` |
| `record_company_version` | [026_company_fields_out.sql:14](../../../edgar_warehouse/mdm/migrations/026_company_fields_out.sql#L14) | 81 | `write_batch` |
| `record_detail_versions` | [022_detail_version.sql:58](../../../edgar_warehouse/mdm/migrations/022_detail_version.sql#L58) | 37 | `keep_detail_versions` |
| `record_relationship_version` | [010_relationship_version.sql:50](../../../edgar_warehouse/mdm/migrations/010_relationship_version.sql#L50) | 36 | `keep_relationship_version` |
| `record_stage` | [001_mdm.sql:1059](../../../edgar_warehouse/mdm/migrations/001_mdm.sql#L1059) | 46 | `keep_stage` |
| `release_binding` | [001_mdm.sql:1106](../../../edgar_warehouse/mdm/migrations/001_mdm.sql#L1106) | 32 | `keep_stage` |
| `write_batch` | [019_merge_stage_no_limit.sql:15](../../../edgar_warehouse/mdm/migrations/019_merge_stage_no_limit.sql#L15) | 201 | `preview_batch`; `save_batch` |
### Indexed retrieval and context

6 routines; 129 latest source lines. Next tickets: 03 / 05. Replace caller-specific PostgreSQL reads with exact indexed selected-engine operations; preserve lookup completeness and context semantics.

| Routine | Latest definition | Lines | Python source references / internal caller |
|---|---|---:|---|
| `cross_reference_lookup` | [005_cross_reference.sql:47](../../../edgar_warehouse/mdm/migrations/005_cross_reference.sql#L47) | 14 | edgar_warehouse/context.py:276 |
| `decisions_naming` | [012_key_join_lookups.sql:52](../../../edgar_warehouse/mdm/migrations/012_key_join_lookups.sql#L52) | 10 | edgar_warehouse/mdm/clean/scope.py:174 |
| `entity_search` | [007_entity_context.sql:96](../../../edgar_warehouse/mdm/migrations/007_entity_context.sql#L96) | 51 | edgar_warehouse/context.py:418 |
| `reading_link_subjects` | [003_lookup_indexes.sql:17](../../../edgar_warehouse/mdm/migrations/003_lookup_indexes.sql#L17) | 11 | `readings_naming` |
| `readings_naming` | [012_key_join_lookups.sql:26](../../../edgar_warehouse/mdm/migrations/012_key_join_lookups.sql#L26) | 9 | edgar_warehouse/mdm/clean/scope.py:240 |
| `relationship_chain` | [006_relationship_context.sql:97](../../../edgar_warehouse/mdm/migrations/006_relationship_context.sql#L97) | 34 | SQL reader, trigger/index or stored capability dependency; preserve until its replacement ticket accounts for it. |
### Atomic enforcement, assessment and lifecycle

14 routines; 356 latest source lines. Next tickets: 02 / 04 / 06. Preserve destination authority and atomic behavior in the replacement capabilities. These guarantees are not a blanket deletion target.

| Routine | Latest definition | Lines | Python source references / internal caller |
|---|---|---:|---|
| `claim_outbox` | [014_outbox_names_batch.sql:218](../../../edgar_warehouse/mdm/migrations/014_outbox_names_batch.sql#L218) | 20 | SQL reader, trigger/index or stored capability dependency; preserve until its replacement ticket accounts for it. |
| `claim_outbox_input` | [016_publication_inputs.sql:42](../../../edgar_warehouse/mdm/migrations/016_publication_inputs.sql#L42) | 26 | edgar_warehouse/mdm/clean/store.py:501 |
| `finish_outbox` | [001_mdm.sql:762](../../../edgar_warehouse/mdm/migrations/001_mdm.sql#L762) | 18 | edgar_warehouse/mdm/clean/store.py:517; edgar_warehouse/mdm/clean/store.py:529 |
| `finish_run` | [001_mdm.sql:781](../../../edgar_warehouse/mdm/migrations/001_mdm.sql#L781) | 19 | edgar_warehouse/mdm/clean/run.py:186 |
| `force_publish` | [018_publish_changed_records.sql:315](../../../edgar_warehouse/mdm/migrations/018_publish_changed_records.sql#L315) | 65 | edgar_warehouse/mdm/clean/cli.py:113 |
| `immutable_row` | [001_mdm.sql:801](../../../edgar_warehouse/mdm/migrations/001_mdm.sql#L801) | 5 | SQL reader, trigger/index or stored capability dependency; preserve until its replacement ticket accounts for it. |
| `preview_batch` | [001_mdm.sql:870](../../../edgar_warehouse/mdm/migrations/001_mdm.sql#L870) | 14 | edgar_warehouse/mdm/clean/merge.py:563 |
| `queue_outbox` | [018_publish_changed_records.sql:88](../../../edgar_warehouse/mdm/migrations/018_publish_changed_records.sql#L88) | 16 | `force_publish`; `write_batch` |
| `record_attempt` | [001_mdm.sql:924](../../../edgar_warehouse/mdm/migrations/001_mdm.sql#L924) | 29 | edgar_warehouse/mdm/clean/run.py:50 |
| `record_match_proposal` | [020_merge_record_by_record.sql:80](../../../edgar_warehouse/mdm/migrations/020_merge_record_by_record.sql#L80) | 44 | edgar_warehouse/mdm/clean/assessment.py:24 |
| `require_configured_kind` | [024_configured_kinds.sql:19](../../../edgar_warehouse/mdm/migrations/024_configured_kinds.sql#L19) | 10 | SQL reader, trigger/index or stored capability dependency; preserve until its replacement ticket accounts for it. |
| `save_batch` | [020_merge_record_by_record.sql:23](../../../edgar_warehouse/mdm/migrations/020_merge_record_by_record.sql#L23) | 56 | edgar_warehouse/mdm/clean/store.py:485 |
| `start_run` | [001_mdm.sql:1226](../../../edgar_warehouse/mdm/migrations/001_mdm.sql#L1226) | 19 | edgar_warehouse/mdm/clean/run.py:96 |
| `supersede_match_proposal` | [020_merge_record_by_record.sql:125](../../../edgar_warehouse/mdm/migrations/020_merge_record_by_record.sql#L125) | 15 | edgar_warehouse/mdm/clean/assessment.py:53 |

### Trigger and index obligations

- `stage_record` writes call `stage_fold`, which calls `stage_claim` and `stage_profile_key`; `keep_stage` also applies bindings and releases. Shared preparation must retain latest revision/mapping order and bronze provenance.
- Current-record triggers retain relationship and detail versions. Preserve their set-difference semantics and open-history uniqueness in one transaction before replacing the trigger paths.
- `reading_link_subjects` participates in indexed relationship/scope retrieval. Replace dependent expressions/indexes before retiring it.
- `immutable_row` and `require_configured_kind` are integrity guards. Preserve their outcomes and restricted grants.
- `save_batch` and assessment functions also enforce ready/unapplied proposals, exact assessed effects, identity publication floors and root-run observations. Generic generation checks alone do not cover them.

### Demonstrated worker dependency outside the MDM schema

`bookkeeping/clean/destinations.py` installs a PostgreSQL-16-only guard and calls `bookkeeping_guard.authorize` in the same transaction as effects. Its three functions are `authorize`, `valid_at_commit` and `claim_publication`; they are outside the 36 MDM functions above. Protocol 4 now qualifies the minimal PostgreSQL/MySQL destination-authority helper, but normal worker, publication and guard-migration integration remains the worker-authority ticket. Whole Bookkeeping conversion stays outside this map.

## Preserved work allocation

| Existing work | State after landing | Remaining owner |
|---|---|---|
| Pinned PostgreSQL candidate selectors and migration 027 | Merged in PR #1148; configured normal PostgreSQL behavior qualified | Indexed-record ticket integrates the rest; retirement ticket handles superseded native caller paths |
| Native candidate routes, retained latest-reading reindexing and RecordReader transport | Merged; restricted real-engine helper and binding/correction module checks pass | Indexed-record ticket connects the entire normal proposal/scope path |
| Protocol-4 destination authority and explicit input publication | Merged; PostgreSQL/MySQL helper qualified; SQL Server protocol 4 refused | Worker-authority and atomic-merge tickets connect normal worker/publication/assessment semantics |
| Reusable guidance | Separate PR #1150 merged as acd96aa8 after explicit operator approval; all nine checks passed | Final completion/skill-learning ticket accounts for its outcome |

The merged tree matches qualified revision `149ff418` exactly. The private pending patch passes a reverse apply check against the merged tree, and the separately preserved new test matches its committed hash. The original implementation worktree is clean; the fresh inventory branch carries no runtime changes. Shared-main fix-pipelines WIP and unrelated artifacts remain untouched. The former uncommitted MDM work is now retained in the merge, so later tickets start from current main instead of reapplying an old draft.

## Required behavior matrix

| Case | Current evidence | Remaining proof / ticket |
|---|---|---|
| Configuration and arbitrary vocabulary | Invented pair profiles reach normal PostgreSQL candidate retrieval; shared native paths are configured | Normal owner registration and complete MySQL merge: storage, indexed-record and atomic-merge tickets |
| Candidate arrival order, held values, route changes and replay | 49 affected PostgreSQL workflow tests; configured route reindex/transport included in each 98-case adapter cohort | Full installed caller on both engines: installed qualification |
| Revision fold, identity, fields/profiles and relationships | 994 MDM unit cases and shared native preparation; old PostgreSQL paths remain | One complete normal caller and durable parity, including every configured kind/source fixture |
| History and details | Native preparation and existing PostgreSQL versioning; mixed SQL routines inventoried above | Atomic current/history/detail/relationship write and rollback on both engines |
| Freshness and competing proposals | Scope/generation and restricted save checks exist; helper conflicts qualified | Reproduce name/census change between `propose` and save; prove stale proposal is refused/retried, including the no-identity-work path. This is an unproven failure mode, not a confirmed defect. |
| External authority | Helper covers overtaking, late expiry, malformed direct requests, same-token ownership, caller-held transaction and duplicate retry | Normal worker/guard migration and publication integration |
| Publication and root-run replay | Input-versus-index helper publication, consumer payloads and replay pass | Preserve native input accounting, original payload bytes/hashes and root-run association through normal caller |
| Populated upgrade and rights | PostgreSQL candidate upgrade and adapter upgrade/recovery/grants qualified | Normal MySQL owner migration plus retained-state two-engine workflow upgrade |
| Real master links, context and operator health | PostgreSQL-specific normal reads identified; helper lookups are not complete caller proof | Real Silver lookup/refresh, context/history/detail/health commands on both engines |
| Independent installation | Two installed-bundle cases pass; full normal MySQL merge remains refused | Installed normal two-engine workflow matrix before any retirement |
| SQL Server | 88 retained adapter cases pass; protocol 4 explicitly refused | Full workflow stays after PostgreSQL/MySQL completion |

Qualification counts refer to merged PR #1148: all nine CI checks passed. Inventory catalog checks establish installed function membership and unchanged repeat migration, not end-to-end mastering parity.

## Review

### Standards

Fresh worktree/branch from merged main; claim recorded before inventory. Counts and source-only references, no source records or private connections. Existing WIP and rollback anchors are preserved. Catalog proof used a disposable server and stopped it. No runtime files or historical migrations change.

### Spec

All 36 installed function names have a disposition and replacement ticket; every normal caller operation has an explicit gap and qualification gate. Preparation, indexed retrieval, mixed persistence and storage guarantees are distinguished. Full MySQL support and routine removal remain incomplete.

### GoF

The existing adapter/native facade was extended in #1073, #1096, #1121 and #1148. Reuse that boundary; the present cost is unfinished caller transport and atomic protocol integration. A second store hierarchy or policy interpreter would add migration/review cost without removing those obligations. No refactoring is proposed by this inventory.
