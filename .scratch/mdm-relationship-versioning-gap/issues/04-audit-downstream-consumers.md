Type: research
Status: open

## Question

Do the downstream consumers of "current" `mdm_relationship_instance` state
(the Snowflake gold export via `mdm export`, graph sync via
`mdm sync-graph`/`mdm publish-relationships`, and the operator MDM/graph
review dashboard) already reflect this quarantine bug's stale data as their
own "current" state, or is there some independent correction path that
already masks it? Bears directly on how urgent this map's fix is --
199,252 quarantined rows in Postgres is one thing; whether that has already
propagated into gold tables/the graph/the dashboard operators and
downstream consumers actually look at is another.

## Context

Every "current" reader found so far in the MDM codebase (`coverage.py`,
`generation.py`, `neighbor_expansion.py`, `pipeline.py`'s own
`current_relationships()`) filters `quarantined = False` -- so structurally,
nothing currently reads a quarantined row as "current." The open question is
whether that's actually a *problem* for downstream freshness (a
quarantined-away newer version means the *older*, non-quarantined version
is what gold/graph/dashboard already show as current -- stale but not
literally invisible) versus something worse (e.g. a relationship
disappearing from exports entirely in some edge case). Not yet traced end
to end.

## Answer

(not yet resolved)
