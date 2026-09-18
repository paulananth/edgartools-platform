# Build the isolated PostgreSQL foundation

Type: task
Status: resolved
Owner: Codex
Blocked by: 01

## Work

Implement real versioned migrations, retained assertions, stable IDs, journal/checkpoint/commit evidence and publication intent on one transaction. Restricted-role PostgreSQL16 tests must run without prerequisite skips.

## Evidence

Implemented migrations 023/025 and mirror 024, protected runtime capabilities, immutable evidence/decisions, atomic bounded batches, checkpoint and generation fencing, publication leases/receipts, and existing Bookkeeping integration. The 19-test real PostgreSQL suite has zero skips. Installed schemas in the user-supplied local databases without changing legacy counts. See [evidence](../../../docs/specs/clean-mdm/evidence.md).
