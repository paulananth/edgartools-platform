# Legacy inventory and replacement qualification

Snapshot: refreshed main `94b5633d`, dedicated branch `codex/fresh-change-journal`.
This is a code inventory, not a live privilege or deployment audit. Physical
legacy stores remain audit archives indefinitely by default.

[`legacy-inventory.json`](legacy-inventory.json) records all 13 legacy tables,
direct model/SQL references, DDL and grant locations. [`caller-inventory.json`](caller-inventory.json)
records imports of the legacy ledger, registry, revision, processing, conflict,
import and mirror interfaces. Transitive family drivers are listed below.

The replacement contracts and isolated tests exist. Their existence does not
qualify every original caller or approve feed cutover.

| Legacy table | Replacement owner | Preserved invariant | Local qualification |
| --- | --- | --- | --- |
| `public.source_observation_cursor` | Bookkeeping resource checkpoint | Monotonic, no holes, leased CAS across runs | acquisition: resource_checkpoint_cas_across_runs |
| `public.source_fetch_decision` | Frozen source-owned decision + journal authorization | Role/cause/disposition, original candidate key, approved scope | acquisition: authorization, invalid requests, conditional outcomes |
| `public.source_fetch_work` | Bookkeeping work_item / lease | Owner/token/expiry takeover and stale completion rejection | configured: renewal_takeover_and_stale_completion |
| `public.source_fetch_transition` | Journal authorization/outcome; Bookkeeping recovery | Immutable transition evidence; terminal state needs evidence | journal: duplicate/conflict; acquisition: lost acknowledgements |
| `public.source_revision` | Source-owned revision manifest + Bookkeeping checkpoint | Pinned raw/canonical/domain versions and scoped predecessor | source_evidence: source.revision and invalid predecessor/checkpoint |
| `public.source_processing_decision` | Configured Bookkeeping steps / frozen inputs | Expected producers sealed before completion; versions and business keys retained | configured: stage inputs, prerequisites and corruption |
| `public.source_expected_producer` | Configured producer work + source completeness manifest | Exact expected/verified counts including explicit zero scopes | source_evidence: producer.verified / scope.empty; missing proof |
| `public.source_registry_version` | Rules source documents / rule_version | Exact version/digest proof and independent approval | configured: pipeline_rules_and_approval_authority; MDM qualification |
| `public.source_registry_coverage` | Rules acquisition feeds / proof; Bookkeeping catch-up | Declared families/producers, complete catch-up before activation | acquisition: current_rules_capture_policy; Rules governance |
| `public.source_evidence_conflict` | Source-owned conflict/resolution manifests | Both hashes retained, exact scoped operator authorization | source_evidence: conflict/resolved and invalid authorization |
| `public.source_evidence_import` | Source-owned import manifest + configured work | Foreign environment/checksum verified before local immutable copy | source_evidence: imported and corrupt/changed authorization |
| `bookkeeping_mirror.event` | Shared journal.event | Original key, duplicate same-content, conflict fails, read-back before acknowledgement | configured: full_completion_and_duplicate_delivery / journal_failure |
| `mdm_mirror.event` | Shared journal.event with JournalPublisher | Original journal/batch key, committed owner payload hash and root scope | MDM: Rules-backed registration, committed ingestion, lost journal acknowledgement |

## Original-stack callers still requiring replacement and feed qualification

- `application/workflows/capture_filing_artifact.py` and the five
  `drive_*_discovery.py` entrypoints still use the original AcquisitionLedger,
  registry catch-up, revisions and Silver finalizers.
- `acquisition/{discovery,submissions_discovery,company_facts_discovery,
  reference_catalog_discovery,adv_bulk_dataset_discovery}.py` and their Silver
  acceptance modules retain original facade/ledger interfaces. They must run
  on the original stack until corresponding complete fresh stages qualify.
- `acquisition/{processing,revisions,registry_ledger,evidence_conflicts,
  evidence_import,capture_parity}.py` remain legacy interfaces. Capture uses
  only the old pure decision validation helpers; it performs no legacy SQL.
- `mdm/clean/source_publications.py`, native `PublicationVerifier`, standalone
  Clean MDM CLI/RunCoordinator and legacy MDM pipelines retain source-table
  verification/control. Configured `mdm.ingest` and `mdm.publish` have a tested
  Rules/journal route; standalone legacy runs have not been redirected.
- Legacy MDM migrations 013–017 and their runtime application functions
  remain original-stack provisioning. Fresh local control provisioning does
  not call them. Original Bookkeeping and mirror migration functions remain
  explicitly legacy drain interfaces; they reject the clean database names.

## Privilege and retirement boundary

Legacy acquisition role owners are `edgartools_acquisition_owner` and
`edgartools_acquisition_registry_owner`; coordinator, worker, operator,
processor and Silver-finalizer roles have separate grant/column/function
boundaries (migrations 013–017). The detailed grant pointers remain in JSON.
Fresh journal runtime receives only append/get/bounded-list/status functions;
fresh Bookkeeping runtime executes fenced control functions; Rules keeps the
independent `rules_approver` membership. Legacy role memberships must not be
carried to fresh runtime logins.

Before disabling each original caller, qualify its parser, destination effects,
producer/barrier counts, unchanged/empty semantics, operator authority, drift
and recovery using the exact feed configuration and frozen baseline manifest.
Before live retirement, inventory live grants and functions, drain historical
intent on its original image/stores, then revoke runtime access after qualified
promotion. No DROP, legacy history import, privilege revocation or deployment
has been executed by this workstream.
