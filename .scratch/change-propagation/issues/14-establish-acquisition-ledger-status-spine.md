# 14 — Establish the acquisition ledger and status spine

**What to build:** Make PostgreSQL authoritatively decide and report whether a
discovered source candidate may be fetched. Demonstrate the complete path with
a candidate that reaches an explicit terminal no-download disposition without
performing a network request.

**Blocked by:** 13 — Expand acquisition command registration

**Status:** resolved

- [x] A valid captured-discovery, due-policy, or operator cause can create one
  immutable Source Fetch Decision with a monotonic observation position.
- [x] Database constraints and role ownership reject unauthorized transitions,
  duplicate active fetches for one logical key, and stale fencing tokens.
- [x] `ALREADY_CAPTURED_VERIFIED`, `OUT_OF_SCOPE`, and `OPERATOR_EXCLUDED` are
  the only terminal no-download outcomes; deferred work remains visibly open.
- [x] Source Change Status reports cause, fetch disposition, blocker, and next
  action for every candidate in the demonstration path.
- [x] PostgreSQL unavailability prevents creation or execution of new source
  requests, and tests prove that no source adapter is invoked.
