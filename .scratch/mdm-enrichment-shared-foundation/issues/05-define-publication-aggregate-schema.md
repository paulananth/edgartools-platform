# Define the publication-aggregate schema (table names, keys, FKs)

Type: grilling
Status: open
Blocked by: none (01 and 02 resolved)

## Question

The GoF review's finding 4 and Appendix C item 1: exact table names, keys,
foreign keys, and temporal-uniqueness rules for the 7-record minimum schema
boundary — source publication, publication artifact, source record version,
consumer candidate, stewardship decision, accepted binding/version, consumer
checkpoint.

**Revised 2026-09-19, after tickets 01/02 resolved and the Clean MDM
decommission directive.** The question is no longer "define 7 tables." Read
against Clean MDM's installed `mdm_v2` DDL (migrations 023/026/027 on
`origin/codex/clean-mdm-integration`, read-only) and the existing
`change_ledger` (migration 013), most of the boundary already exists:

| GoF record | Where it already lives | Gap |
| --- | --- | --- |
| Source record version | `mdm_v2.assertion` (`UNIQUE(source_code, record_key, publication_key)`, `revision`) | none |
| Stewardship decision | `mdm_v2.decision` (`operation IN bind/merge/reverse/override/revoke/exclude/retire_source`) | none |
| Accepted binding/version | `mdm_v2.identity` + `mdm_v2.projection` (current), `mdm_v2.decision` body (history) | none |
| Consumer candidate | **not persisted** — resolved inside `MergeStage.apply()`'s single transaction; `mdm_v2.deferred_record` holds only the blocked disposition | already proposed to Codex as [pre-merge staging](../../clean-mdm-premerge-staging-proposal/map.md), handed over via `.scratch/handover/2026-09-19-claude-to-codex-mdm-premerge-proposal.md` |
| Consumer checkpoint | `mdm_v2.checkpoint (consumer PRIMARY KEY, position, batch_id)` | **keyed by consumer alone** — cannot express ticket 02's independent publication families or ticket 03's "never advance a sibling family." Clean MDM's own `recovery.md` line 20 already describes the checkpoint as carrying "family/epoch and source position," so the DDL lags their spec rather than contradicting it |
| Publication artifact | `change_ledger.source_revision` — one `bronze_artifact_reference` per revision | one row per artifact exists; **no row ties several artifacts to one publication** |
| Source publication | `mdm_v2.dataset` (the contract) + `publication_key` string on `assertion`/`deferred_record`; `change_ledger.source_registry_coverage` (per-family coverage) | **no publication row** carrying manifest hash, member inventory, `verified_complete` lifecycle, superseded publication — Clean MDM's `source-evidence.md` says "complete-publication accounting remain[s] integration work" |

Root run: `023_clean_mdm.sql` line 2 ("No parallel root-run table: run_id
refers to the existing Bookkeeping owner") and `026` line 1 independently
reached ticket 01's answer.

So the open decisions are:

1. **Checkpoint key shape.** Per-family checkpointing needs `mdm_v2.checkpoint`
   to change. That is Codex/Grok's protected surface — does this map
   *specify the required key* and hand it over as a proposal (the pre-merge
   staging precedent), or does the foundation keep per-family cursors on
   the acquisition side (`change_ledger.source_observation_cursor`, already
   keyed `(source_family, logical_source_key)`) and leave `mdm_v2.checkpoint`
   as a consumer-level batch watermark?
2. **Publication + publication-artifact inventory.** The one genuinely new
   schema this map owns. Where does it live — `change_ledger` beside
   `source_revision` (acquisition side, consistent with ticket 01), or
   `mdm_v2` (another Codex-owned change)?
3. **How the spec refers to the five existing `mdm_v2` records** — restate
   them as a versioned contract the foundation depends on, or redefine them?
