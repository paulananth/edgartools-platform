# Decide Step Functions Structural Simplification

Type: grilling
Status: open
Blocked by: 11, 14, 15, 17

## Question

How should the retained state machines be standardized so repeated ECS task
states, MDM chains, profile selection, input defaults, Map configuration,
retry/catch behavior, output summaries, and revision pinning have one clear
contract without erasing workload-specific safety boundaries?

Decide where shared generation is appropriate, where separate state machines
remain valuable, whether any workflow can safely use a different Step
Functions execution type, and how dead or contradictory selection paths are
removed. Preserve immutable release references, bounded replay, state-level
failure visibility, and an operator-readable execution history.
