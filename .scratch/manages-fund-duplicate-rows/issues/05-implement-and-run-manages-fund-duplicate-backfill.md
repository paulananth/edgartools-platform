Type: task
Status: resolved (implementation only — see Answer for what remains)
Blocked by: 04

Graduated from [Ticket 04](04-decide-and-run-backlog-cleanup.md)'s
resolved design.

## What to build

A new write-capable backfill module/CLI, separate from Ticket 03's
read-only `manages_fund_duplicate_monitor.py`, that resolves the existing
~140,907-relationship_id MANAGES_FUND duplicate-active-row backlog:

1. For each `relationship_id` with 2+ currently-active
   (`is_active=TRUE, quarantined=FALSE, superseded_by_version_id IS NULL`)
   MANAGES_FUND rows: pick the row with the lexicographically smallest
   `instance_id` as the keeper; call
   `supersede_relationship_version(session, loser.instance_id, keeper.instance_id)`
   on every other row in the group. Do not call
   `close_relationship_version`/set `valid_to_date`. Do not touch any
   quarantined row.
2. `--dry-run` mode that reports what would change (group count, row
   count) without writing, bounded by a `--limit` on relationship_ids
   examined (per this repo's own documented lesson: an unbounded
   `--dry-run` against a live table defeats its own purpose as a cheap
   correctness check).
3. Real-run mode, also accepting `--limit` for a bounded first pass.
4. No forced graph resync — rely on the next regularly-scheduled
   `sync-graph`/`publish-relationships`.

## Acceptance

- [x] `--dry-run --limit N` reports correct counts against real prod data
      for a small N, without writing anything.
- [x] Real run with a small `--limit` verified live against prod: exactly
      the targeted groups' loser rows get `superseded_by_version_id` set
      to the keeper's `instance_id`; `is_active`/`valid_to_date` untouched
      on every row; quarantined rows untouched.
- [ ] Full backlog run (no `--limit`) verified live: 0 remaining groups
      with 2+ currently-active MANAGES_FUND rows.
- [x] `/gof-refactor-reviewer` consulted before editing (repo hard rule).
- [x] `/code-review` (Standards, Spec, GoF) run before PR is ready.

## Answer

Built `edgar_warehouse/mdm/manages_fund_duplicate_backfill.py` (new,
write-capable, separate from Ticket 03's read-only monitor) plus a new
`mdm backfill-manages-fund-duplicates` CLI subcommand, mirroring
`relationship_quarantine_backfill.py`'s CLI/keyset-pagination/batch-commit
shape while deliberately omitting its chronological-walk/priority-cache/
skip-reason machinery — Ticket 04 confirmed every duplicate group is
byte-identical evidence, so there is nothing to resolve, only a
deterministic keeper (lexicographically smallest `instance_id`) to pick.
Every other row in a group gets `superseded_by_version_id` set via the
existing `supersede_relationship_version` helper; `close_relationship_version`/
`valid_to_date` are never touched; quarantined rows are excluded from both
the candidate query and the resolution query. `--limit` bounds both
`--dry-run` and the real run (an improvement over the sibling module,
whose dry-run is unbounded — directly avoids this repo's own documented
"unbounded --dry-run defeats its own purpose" lesson).

Pre-code `/gof-refactor-reviewer` consult: don't share query logic with
the sibling monitor (different shapes, no repeated-change evidence); don't
mirror the heavier conflict-resolution machinery (no conflicts exist here);
do mirror the CLI/pagination/batch-commit shape.

Post-diff 3-axis `/code-review` (Standards/Spec/GoF): zero blocking
findings on any axis. Standards noted three judgement calls (no
in-code re-verification of the byte-identical-evidence precondition the
ticket asserts as fact; no audit-trail entry unlike the sibling module's
convention; minor dataclass boilerplate duplication) — none rose to a
blocking violation. Spec confirmed every acceptance-relevant behavior
(keeper selection, argument order, never touching `is_active`/
`valid_to_date`, quarantined-row exclusion, dry-run non-mutation, `--limit`
bounding both modes, no forced graph resync) matches the ticket exactly.
GoF verdict: leave it — no off-by-one/boundary bugs in pagination, correct
dry-run gating, correct idempotency (a superseded group provably drops out
of future scans, tested via a real double-run), and no premature
abstraction extraction from the two-instance batch-loop shape shared with
the sibling module (no evidenced repeated-change history yet).

Tests: 14/14 passing (SQLite in-memory, mirroring the sibling module's
fixture pattern). Broader regression sweep: `tests/mdm/` + `tests/architecture/`
1386 passed, 3 skipped. Full repo suite: 3451 passed, 8 failed (the same
pre-existing, unrelated Postgres-integration schema-drift failures
documented elsewhere in CLAUDE.md), 12 skipped.

**Live-prod verification, done in two bounded steps (2026-09-12), each
with explicit go-ahead:**

1. `--dry-run --limit 20` against real prod: reported
   `relationship_ids_examined=20`, `rows_superseded=60` (would-be), zero
   writes (confirmed via the SQL event log — SELECT statements only).
2. Real run, `--limit 20` (same 20 groups, keyset-ordered from the start
   with no `after`): reported `relationship_ids_examined=20`,
   `rows_superseded=60` — exact match to the dry-run's prediction.
   Verified directly against Postgres afterward, not just trusting the
   CLI's own report:
   - Remaining MANAGES_FUND duplicate backlog dropped by exactly 20:
     140,907 -> 140,887.
   - Exactly 20 relationship_ids now have any superseded row, totaling
     exactly 60 superseded rows.
   - Every touched group has exactly 1 remaining non-superseded row (the
     keeper) and exactly 1 distinct supersession target — no partial or
     double-superseding.
   - Zero `is_active` flips, zero `valid_to_date` writes, zero
     quarantined rows touched, across every touched group.
   - The surviving row in every touched group is provably the
     lexicographically smallest `instance_id` in its group, exactly as
     designed.
   The DSN was fetched from `edgartools-prod/mdm/postgres_dsn` directly
   into a scratch file each time, read from that file first thing in each
   script, never printed, and deleted immediately after use (both times).

**Not yet done, and deliberately not attempted without further explicit
go-ahead:** the full, unbounded backlog run (remaining ~140,887 groups).
This is the same mechanism already twice-verified live above, just at
full scale — a larger production write than either prior step, so it
still needs its own explicit confirmation rather than being implied by
the small run's success.
