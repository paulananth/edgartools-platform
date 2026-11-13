# Who runs the measurement, and what is handed off when the map closes?

Type: grilling
Status: open
Blocked by: 01, 04, 05, 06, 08, 09

## Question

This map is a planning map. When its decisions are settled, the destination — a decision-complete
measurement specification — is complete, but the measurement itself is not run here unless the
operator says otherwise. This ticket settles the handoff.

Decide, with the operator:

1. Whether the measurement runs inside this map (which would need the map's Notes overridden to
   permit execution) or is handed off as a specification to a separate execution session.
2. Who runs it, and against which environment and private store folder.
3. What the handoff package contains: the resolved tickets' answers, the evidence files, the
   report shape, the per-target procedure, and the authorization rule for live loads.
4. What the final report is allowed to claim if the gates stayed closed: a retrospective timeline
   with unavailable init timing and no live measurement. Confirm that this is an acceptable end
   state, or state what else must happen first.
5. Whether this map's tickets should be closed, or handed on as open execution items.

Record the resolved handoff in the ticket, and append a one-line gist to the map's Decisions so
far.
