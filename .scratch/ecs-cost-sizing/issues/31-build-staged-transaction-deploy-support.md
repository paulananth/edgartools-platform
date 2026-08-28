# Build Staged-Transaction Deploy Support for Structural Changes

Type: task
Status: open
Blocked by: none

## Question

Build the staged-transaction deployment mechanism Ticket 04 already
identified as missing and Ticket 19 named as a hard prerequisite for its
Wave 5 (structural simplification, Ticket 18's shared task-state template
rollout): "Generate and validate every intended definition before changing
live references. Record the update set as one transaction, then
recursively audit all 26 production definitions against the expected exact
task-definition ARNs and ASL hashes. **The current sequential
all-workflow deploy path is not a valid canary mechanism and needs
staged-transaction support before it can implement this policy.**"

Ticket 04 specified this for task-profile changes narrowly; Wave 5's
blast radius is broader (every field the shared template controls —
retry policy, input defaults, Map configuration, output shape — not just
task-definition ARNs), so the audit step this mechanism performs needs to
generalize accordingly. Scope: `infra/scripts/deploy-aws-application.sh`'s
current deploy path (sequential, one workflow at a time, no all-or-nothing
transaction semantics today). Blocks only Wave 5 of the rollout — Waves
1-4 do not depend on this.
