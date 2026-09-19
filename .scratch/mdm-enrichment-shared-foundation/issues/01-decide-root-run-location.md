# Decide where the persistent root run and phase-attempt model live

Type: grilling
Status: open
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
