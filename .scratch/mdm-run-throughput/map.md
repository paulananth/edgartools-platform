# MDM run throughput

## Destination

A locked decision on whether/how to safely speed up `MDMPipeline`'s
remaining single-threaded, per-row resolver loops (`run_securities`,
`run_persons`) the same way `run_companies` was fixed (PR #376) --
covering the correctness constraint each domain's match-candidate lookup
imposes on concurrent execution. Explicitly out of scope for the
[pipeline-throughput-architecture](../pipeline-throughput-architecture/map.md)
map ("MDM / graph-sync stages ... run on a separate Postgres+graph path
with their own cost model" -- that map's own Out of scope section flagged
"a future map can cover them if warranted"; this is that map).

## Notes

- Domain: `edgar_warehouse/mdm/pipeline.py` (MDMPipeline.run_securities,
  run_persons), `edgar_warehouse/mdm/resolvers/security.py`,
  `edgar_warehouse/mdm/resolvers/person.py`.
- Root cause of the underlying slowness (shared by all of MDM's per-row
  resolver loops, not just company): every MDM Postgres SQL round trip
  measures a flat ~68ms regardless of work done -- the MDM Postgres
  endpoint resolves to `us-west-2`, ECS warehouse tasks run in `us-east-1`.
  Real, structural cross-region latency, not a pooling misconfiguration.
  Concurrency hides this; it doesn't reduce it.
- Standing preference from the parent session: real measurements, not
  estimates.

## Decisions so far

1. [Fix run_companies concurrency](https://github.com/paulananth/edgartools-platform/pull/376) — resolved (implemented directly, not decision-spec-only, given live production time pressure): company resolution moved to a bounded `ThreadPoolExecutor` (default 8 workers, one session per worker). Safe because `CompanyResolver._existing_candidates` scopes its match lookup to the row's own CIK -- a true 1:1 natural key, no cross-row shared match state, and CIK-exact rematching makes retries idempotent. Real measured baseline: 62,190 companies at ~2.16s/row (~37h projected) before the fix.

## Not yet specified

- Whether `run_securities` can be safely parallelized, and how. Checked and
  explicitly NOT safe to apply the same per-row-independent-thread pattern
  as company: `SecurityResolver._existing_candidates` matches on
  `(issuer_entity_id, canonical_title)`, a genuine many-to-one key -- many
  different ownership-transaction rows (different accession/owner_index/
  txn_index) legitimately collapse onto ONE security entity per
  (issuer, title) pair. Concurrent workers processing different rows that
  share the same (issuer, title) key would each see an empty candidate set
  (uncommitted sibling work invisible across sessions) and could create
  duplicate security entities that a sequential run would have deduped.
  Needs either a DB-level unique constraint + upsert/ON CONFLICT pattern, or
  pre-grouping rows by (issuer_entity_id, canonical_title) and parallelizing
  across groups while serializing within a group -- not sharp enough to
  ticket without picking one of those.
- Whether `run_persons` can be safely parallelized, and how. Checked and
  explicitly NOT safe as-is: `PersonResolver._existing_candidates`
  (`edgar_warehouse/mdm/resolvers/person.py:113`) scopes to `owner_cik` when
  present (same safe CIK-natural-key shape as company) but falls back to an
  UNSCOPED table-wide fuzzy name match across every existing person when
  `owner_cik` is `None` -- SEC Form 3/4/5 filers without their own
  registered CIK hit this path. Concurrent workers under that fallback could
  create duplicate person entities for near-identical names a sequential run
  would have fuzzy-merged. Real row count is small (~7,911 driving rows,
  ~4.7h sequential) -- lower priority than security's ~9h, but the same
  correctness question needs answering before touching it.
- Real per-domain row counts and sequential-runtime baselines for
  `run_securities`/`run_persons` were estimated from raw table counts during
  the parent investigation (~15,000 and 7,911 respectively) -- not yet
  measured the same rigorous way ticket-style (real `mdm_progress` log
  deltas) as company's 62,190/2.16s baseline was.

## Out of scope

- `run_advisers`/`run_funds` -- already implemented as a bulk/batched
  operation (`edgar_warehouse/mdm/adv_bulk.py`, `_chunks`/`_WRITE_BATCH_SIZE`),
  not the naive per-row `resolve_one` loop shape this map is about. Not
  subject to the same bottleneck despite adviser's large raw row count
  (234,396 ADV filings) and fund's very large one (1,579,876 private funds).
- Reducing the underlying ~68ms cross-region round-trip latency itself
  (e.g. relocating the Snowflake Postgres instance's region, or relocating
  ECS compute to us-west-2) -- a much larger infrastructure decision than
  this map's scope, and concurrency already provides most of the practical
  win without it.
