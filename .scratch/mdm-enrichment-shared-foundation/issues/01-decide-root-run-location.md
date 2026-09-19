# Decide where the persistent root run and phase-attempt model live

Type: grilling
Status: open
Blocked by: none

## Question

The GoF review's finding 5: source fetch decisions, source revisions,
normalized record versions, candidates, stewardship decisions, accepted
bindings, checkpoints, Snowflake exports, graph publication, and deletion
decisions must all resolve to **one durable root run** with append-only
phase attempts — a string `run_id` repeated across tables isn't enough
without a persistent record defining the run itself (source trigger, parent
execution, image/parser/config identity, start/terminal state, phase
attempts).

Where does that persistent root-run record live? The review names three
candidates (its Appendix C, item 2) without picking one:

1. **The acquisition schema** (`edgar_warehouse/acquisition/`, Postgres) —
   where fetch decisions and source revisions already live.
2. **The MDM schema** (legacy `edgar_warehouse/mdm/database.py`) — where
   `mdm_change_log`/`mdm_relationship_instance` already carry `run_id` per
   ADR 0007.
3. **A new shared control schema**, accessible to both, that is neither's
   authority.

This is foundational: it shapes where the publication-aggregate tables
(ticket 05) and role grants (ticket 07) ultimately live.

## Comments
