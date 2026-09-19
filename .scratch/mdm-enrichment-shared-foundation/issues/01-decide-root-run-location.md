# Decide where the persistent root run and phase-attempt model live

Type: grilling
Status: resolved
Blocked by: none

## Question

**Revised 2026-09-19** — the map's own Notes now lock legacy MDM as being
decommissioned; Clean MDM (`mdm_v2`) is the sole MDM target. The original
review evidence (ADR 0007, legacy `mdm_change_log`/`mdm_relationship_instance`)
targeted the schema being retired, so option 2 below is replaced, not just
relabeled — and a new fact changes the shape of the question: Clean MDM's
own `MergeStage.apply()` (`edgar_warehouse/mdm/clean/merge.py:108`) already
takes a `run_id` parameter today. It is *not* itself a persistent root-run
record with the rich metadata the review wants (source trigger, parent
execution, image/parser/config identity, phase attempts) — it's a
caller-supplied string, used inside the atomic commit. So the question isn't
purely "where does a new table live," it's also "does the foundation's root
run become the authority Clean MDM's `run_id` parameter is *checked against*,
or something looser."

The GoF review's finding 5: source fetch decisions, source revisions,
normalized record versions, candidates, stewardship decisions, accepted
bindings, checkpoints, Snowflake exports, graph publication, and deletion
decisions must all resolve to **one durable root run** with append-only
phase attempts — a string `run_id` repeated across tables isn't enough
without a persistent record defining the run itself.

Where does that persistent root-run record live?

1. **The acquisition schema** (`edgar_warehouse/acquisition/`, Postgres) —
   where fetch decisions and source revisions already live.
2. **Clean MDM's own schema** (`mdm_v2`, alongside `mdm_v2.batch`/
   `mdm_v2.decision`/`mdm_v2.assertion`) — the foundation's root run becomes
   the record that mints/validates the `run_id` string Clean MDM's
   `MergeStage.apply()` already accepts as a parameter, rather than a
   parallel concept.
3. **A new shared control schema**, accessible to both, that is neither's
   authority.

This is foundational: it shapes where the publication-aggregate tables
(ticket 05) and role grants (ticket 07) ultimately live, and whether Clean
MDM's own owners (Codex/Grok) need to accept a foundation-issued `run_id`
contract into `merge.py` — which, if so, is itself a proposal for them to
accept, not something this map can decide unilaterally (same ownership
boundary as [the pre-merge staging proposal](../clean-mdm-premerge-staging-proposal/map.md)).

## Comments

- 2026-09-19: operator answer — shared control schema, realized as the
  **existing** `bookkeeping` and `change_ledger` databases, unchanged.
  Verified live against the local Postgres instance: `bookkeeping.pipeline_run`
  (`pipeline_run_id`, `command_name`, `started_at`/`completed_at`, `status`,
  `arguments_json`, `environment_name`, ...) already is a persistent root-run
  record with almost exactly the review's wanted fields (source trigger via
  `command_name`/`arguments_json`, start/terminal state, environment
  identity). `change_ledger`'s `source_fetch_decision`/`source_revision`/
  `source_registry_version`/`source_registry_coverage`/`source_fetch_transition`
  tables already carry per-`source_family`/`logical_source_key` evidence
  lineage — `source_revision` alone has `parser_version`, `schema_version`,
  `configuration_version`, `contract_version`, matching the review's
  "image/parser/config identities" ask.

## Answer

**Shared control schema — reuse `bookkeeping` + `change_ledger` as-is, no
schema change.** GLEIF's enrichment pipeline is a new `command_name` value
in `bookkeeping.pipeline_run` (the root run) and new `source_family`
values flowing through `change_ledger`'s existing `source_fetch_decision`/
`source_revision`/`source_registry_version`/`source_fetch_transition` tables
(the acquisition-side evidence lineage). "Add new pipeline and steps that
need to be tracked" means new *rows* — new registry entries, new source
families — not new tables.

This does **not** cover the whole 7-record schema boundary from ticket 05,
though: `bookkeeping`/`change_ledger` are acquisition-side (source capture),
and the review's remaining four record kinds — consumer candidate,
stewardship decision, accepted binding/version, consumer checkpoint — are
MDM-domain-facing, not source-evidence-facing. Per the review's own finding
7 ("current-state MDM tables remain derived projections... add source-grained
evidence plus append-only decisions upstream"), those four likely belong
adjacent to Clean MDM's own `mdm_v2` schema, not a third new schema. Ticket
05 decides this precisely — this ticket only fixes where root-run and
source-evidence lineage live, not the domain-consumer half.

This does not modify `bookkeeping` or `change_ledger`'s existing schema, and
proposes no change to Clean MDM's `mdm_v2` — both remain read/reuse only
from this decision.
