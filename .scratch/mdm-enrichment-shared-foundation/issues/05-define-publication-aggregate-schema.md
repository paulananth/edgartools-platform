# Define the publication-aggregate schema (table names, keys, FKs)

Type: grilling
Status: resolved
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

## Comments

- 2026-09-19, Q1 (checkpoint key): operator chose **(a)** — this map
  specifies the required key and hands it to Codex as a proposal; it does
  not decide `mdm_v2` DDL.
- 2026-09-19, Q2 (publication inventory): first posed as two new
  `change_ledger` tables (`source_publication` + `source_publication_member`).
  Operator challenged: "why GLEIF cannot be verified one file at a time, why
  complicate for no advantage?" Correct challenge — per-file verification
  already works; the only real coupling is *meaning*, not verification (an
  RR "no parent row" is ambiguous until the same date's REPEX file is also
  present — GLEIF Company ticket 07's "coordinate RR with REPEX"). That is
  a read-time precondition, not stored state. Option (a) withdrawn; revised
  Q2 ("derive completeness from existing rows, zero new tables") accepted.
- 2026-09-19, Q3 (how the spec refers to Clean MDM's tables): operator —
  "i did not approve mdm_v2; if it is the new mdm so be it, there is one
  mdm set of tables." Accepted **(a)**: point at them, never redefine.
  Note for the spec: `mdm_v2` is Clean MDM's *schema name* (chosen by that
  build to sit beside legacy until legacy is dropped), not an operator
  decision — the spec should say "the MDM tables" and cite the defining
  Clean MDM migration, not lean on the `_v2` suffix as if it were a second
  MDM.

## Answer

**No new tables anywhere.** The 7-record boundary resolves to existing
rows plus one proposal:

| GoF record | Resolution |
| --- | --- |
| Source publication | **Derived**, not stored: the set of `change_ledger.source_revision` rows sharing `(source_family, source_native_revision)` — one row per file, including the ticket-04 manifest file itself. "Complete" = the manifest row is present and every member it lists has a verified row. Enforced as a read-time precondition in the consumer (the Golden Copy consumer runs only when RR and REPEX for the same publication date both have verified rows), never as a stored status. Supersession = newer publication date. |
| Publication artifact | `change_ledger.source_revision`, as-is. |
| Source record version | The MDM assertion table (Clean MDM migration 023), as-is. |
| Consumer candidate | The [pre-merge staging proposal](../../clean-mdm-premerge-staging-proposal/map.md) already handed to Codex — not re-decided here. |
| Stewardship decision | The MDM decision table (023), as-is. |
| Accepted binding/version | The MDM identity + projection tables (023), as-is. |
| Consumer checkpoint | The MDM checkpoint table (023) **as amended by a proposal this map hands to Codex**: key `(consumer, source_family, publication_family)` with committed publication and continuity proof, per GoF item 3 and this map's tickets 02/03. Clean MDM's own `recovery.md` already describes that shape; the DDL lags it. Writing and handing over that proposal is [ticket 08](08-write-checkpoint-key-proposal-for-clean-mdm.md). |

**How the spec refers to MDM tables**: there is one MDM and one set of MDM
tables — Clean MDM's. The spec points at each table by name and cites the
Clean MDM migration file (and its checksum, so drift is visible) that
defines it. It never restates their columns. `mdm_v2` is that build's
schema name, not a second MDM.

Root run: confirmed a third time — `023_clean_mdm.sql` line 2 and `026`
line 1 both bind `run_id` to the existing Bookkeeping `pipeline_run`.
