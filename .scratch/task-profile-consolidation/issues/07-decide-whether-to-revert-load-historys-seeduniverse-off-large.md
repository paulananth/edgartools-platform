# 07 — Decide whether to revert load_history's SeedUniverse off large now that the root-cause hydrate fix is live

Type: grilling

**What to build:** Not a build — a decision. `load_history`'s own
`SeedUniverse` state (inside `write_load_history_definition`) has been
hardcoded to `wh_large_arn` since 2026-08-09, a same-day emergency bump
after a live exit-137 OOM (`seed-universe`'s dispatch unconditionally
buffering the entire canonical `silver.duckdb` into memory during hydrate,
before any per-command filtering logic ran).

That root cause is now fixed and confirmed live in prod (see ticket 06,
`.scratch/task-profile-consolidation/issues/
06-decide-seed-universe-profile-discrepancy.md`, resolved 2026-08-20):
streaming hydrate (PR #392) plus moving `seed-universe`'s novelty-detection
filter off silver onto MDM (PR #394). Ticket 06 kept
`command_task_profile()`'s standalone-workflow-facing `seed-universe` entry
at `medium` on the strength of that fix plus today's canonical size (1.5GiB,
comfortably inside medium's 4096MB envelope for the one remaining unpatched
risk — the merge/publish step's own full-buffer read/write, deliberately
deferred elsewhere, not proven unsafe).

The `seed-universe-narrow-hydrate` wayfinder map's own stated Destination
explicitly named this exact question — *"reaching the end of this map means
deciding, for seed-universe specifically, whether it can move back to a
smaller profile once both are in place"* — but that map closed its Frontier
("None... this map's destination is reached") without a
`## Decisions so far` entry ever actually answering it. This ticket exists
to close that gap for the `load_history`-specific half of the question
(ticket 06 already closed it for the standalone-workflow half).

**Discovered while:** implementing task-profile-consolidation ticket 06
(2026-08-20), investigating the standalone-vs-load_history `seed-universe`
profile discrepancy. Not independently investigated further at the time —
out of ticket 06's own stated scope (its acceptance criteria name only
`command_task_profile()`'s single entry, not load_history's separate
hardcoded parameter).

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

## Question

Should `write_load_history_definition`'s `SeedUniverse` state be reverted
from `wh_large_arn` back to `wh_task_medium_arn` (converging with
`command_task_profile()`'s `seed-universe` entry, per ticket 06's decision),
or does `load_history`'s own invocation pattern carry a real, still-live
reason to stay on `large` that the standalone workflow doesn't share?

- [ ] Determine whether `load_history`'s `SeedUniverse` state genuinely
      seeds against a larger/different universe than the standalone
      workflow, or any other load_history-specific factor (e.g. running
      concurrently with other Stage 0/1 work on the same task, different
      timing relative to canonical's growth) that could keep the merge/
      publish step's still-unpatched full-buffer risk closer to medium's
      4096MB ceiling than the standalone workflow's invocation
- [ ] Either revert `write_load_history_definition`'s `SeedUniverse` state
      to `wh_task_medium_arn` (if no such difference exists, converging
      both call sites downward per ticket 06's same reasoning), or record
      the specific, load_history-only reason it should stay on `large`
- [ ] If reverted, thread the change through the same genuine-routing proof
      technique tickets 02/03/04 of this same effort established (not just
      a value change with no test coverage) and re-verify byte-identical
      ASL for every other state `write_load_history_definition` builds
- [ ] Once decided, update the `seed-universe-narrow-hydrate` map
      (`.scratch/seed-universe-narrow-hydrate/map.md`) with a
      `## Decisions so far` entry closing its own previously-unresolved
      stated destination, not just this ticket

## Answer

<!-- filled in on resolution -->
