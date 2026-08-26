# 36 — Wire the MDM publication outbox into real MDM commits

**What to build:** Make the already-built, currently-dormant transactional
publication queue (`edgar_warehouse/mdm/publication.py`) actually fire from
real MDM processing, and make an actual coordinator drain it, so
relationship-changing MDM commits become exportable exactly once instead
of never being enqueued at all.

**Blocked by:** None — the design decision is already made (Ticket 06);
this is pure wiring.

**Status:** ready-for-agent

- [ ] Every MDM processing pass tied to one upstream `cause_reference`
  (per Ticket 04's Run identity) calls `request_publication` exactly once
  inside the same transaction as its own commit, carrying `cause_reference`
  in `source_summary` — confirmed via `git grep request_publication` showing
  real callers outside `publication.py` and its own tests for the first
  time.
- [ ] `claim_next_publication_request`/`advance_publication_lifecycle` are
  driven by an actual scheduled coordinator (CLI cron, Step Function, or
  equivalent) rather than only existing as manually-invoked CLI probes
  (`mdm publication-claim`/`-status`) — confirmed via `git grep
  advance_publication_lifecycle` showing a real, non-test caller.
- [ ] A live end-to-end test (or prod dry run) proves a real MDM commit
  enqueues a request, a coordinator claims and advances it through
  `graph_pending → graph_building → graph_verified → graph_active`, and
  `compute_publication_freshness` reports healthy status throughout.

## Notes

Surfaced while resolving [06 — Decide MDM affected-key closure and
publication outbox](06-decide-mdm-closure-and-outbox.md) — see that
ticket's Answer for the full design rationale. Both the writer side
(`request_publication`) and the consumer side
(`claim_next_publication_request`/`advance_publication_lifecycle`) are
fully built and unit-tested in isolation but have zero production callers
today — confirmed via `grep -rln "request_publication(" edgar_warehouse/
tests/` returning only `publication.py` itself and three test files.
