Type: task
Status: resolved (2026-09-07)

**Spawned by:** live observation during the mdm-relationship-incremental-filters
Ticket 04 post-deploy verification run (`mdm-mastering-postwatermark-verify-1788817350`,
2026-09-07) — a CloudWatch Logs Insights breakdown of that run's SQL volume showed
49,425 of ~57,000 SQL calls in the first ~14 minutes (entity-resolution phase only,
before relationship derivation even started) were `SELECT`s against `mdm_source_ref`,
roughly one per row processed across `run_companies`/`run_persons`/`run_securities`.

## Question

Should `BaseResolver._skip_if_unchanged` (`edgar_warehouse/mdm/resolvers/base.py`)
batch its `mdm_source_ref` content-hash lookup the same way the relationship-derivation
single-threaded-tail fix (this file's own CLAUDE.md entry) bulk-prefetched per-row
entity-ID lookups for `IS_INSIDER`/`HOLDS`/`HAS_PARENT_COMPANY`/`EMPLOYED_BY`/
`AUDITED_BY` — instead of the current one-`SELECT`-per-row shape?

## Context

`_skip_if_unchanged` (added in `7ffda2d7`, the skip-if-unchanged fast path for
`run_companies`, later reused by `run_persons`/`run_securities` per their resolvers)
runs once per row inside `resolve_one`:

```python
def _skip_if_unchanged(self, ctx, source_system, source_id, content_hash_value):
    stmt = select(MdmSourceRef).where(
        MdmSourceRef.source_system == source_system,
        MdmSourceRef.source_id == str(source_id),
    )
    ref = ctx.session.execute(stmt).scalars().first()
    if ref is not None and ref.source_content_hash == content_hash_value:
        return ref.entity_id
    return None
```

No batching — one Postgres round trip per row, every row, regardless of whether the
row turns out unchanged (the common case: the observed run's company domain showed
100% `skipped_unchanged` for the first ~19,000 rows). This is the same "one row = one
round trip" shape this file's CLAUDE.md documents fixing repeatedly elsewhere
(`claim_discovery_ciks`'s original N+1, `seed_company_sync_state_bulk_if_missing`,
the daily_incremental per-CIK checkpoint fix, and the relationship-derivation
entity-ID bulk-prefetch fix this exact map's sibling effort already applied to
`_person_entity_id`/`_company_entity_id`-style lookups) — not previously flagged for
`_skip_if_unchanged` itself.

**Why this wasn't caught by the mdm-run-throughput map's own fixes:** decisions 1/2 on
this map (`run_companies`/`run_securities`/`run_persons` concurrency) addressed *wall-
clock* latency by parallelizing round trips across a worker-per-row/group thread pool
(mdm_source_ref's ~68ms cross-region round trip hidden behind 16-way concurrency, per
this map's own root-cause note) — they did not reduce the *total number* of round
trips, which is what this ticket is about. The two are independent levers: concurrency
hides latency, batching reduces round-trip count. This map's Decisions so far already
accepted that reducing the underlying per-round-trip latency itself is out of scope;
reducing round-trip *count* was never evaluated.

**Live measurement, not an estimate** (this map's own standing preference): the
2026-09-07 verification run's first 14 minutes, `mdm_sql_started` events broken down
by `(operation, tables.0)`:

| Table | Operation | Count |
|---|---|---|
| `mdm_source_ref` | select | 49,425 |
| `mdm_entity_attribute_stage` | select | 4,317 |
| `mdm_entity_attribute_stage` | update | 2,765 |
| `mdm_security` | select | 1,578 |
| `mdm_entity` | select | 786 |

**Open design questions for whoever picks this up:**
- What's the natural batching key? `(source_system, source_id)` pairs aren't grouped
  by anything shared across a resolver's row batch the way `_person_entity_id`'s CIK
  reuse was — every row's `source_id` is typically unique (an accession number, a CIK).
  A batch prefetch would need to query `WHERE (source_system, source_id) IN (...)`
  across the whole chunk of rows about to be resolved, not a natural single-key reuse
  like the relationship-derivation fix had.
- Does this interact safely with the existing per-row/per-group worker-thread
  concurrency (decision 2 above)? A batch prefetch would need to happen once per
  worker's assigned row group, before that group's per-row loop, using that worker's
  own session — should not require restructuring the grouping/concurrency shape itself,
  but needs to be verified, not assumed.
- Is the win worth it given decision 2 already hides the latency behind concurrency?
  Real measurement needed: does batching reduce wall-clock time materially at 16-way
  concurrency, or does it mostly reduce Postgres-side connection/round-trip load
  (a real but different cost — worth knowing before committing to the batching design).

## Answer

Implemented on `claude/mdm-skip-if-unchanged-batch` (commit `37c44e1d`).

**Batching key (question 1):** each resolver (`CompanyResolver`/`PersonResolver`/
`SecurityResolver`) got a `_source_id` static method, extracted from what was
previously an inline expression inside `resolve_one` -- the exact same expression,
just named and callable from outside the method. `MDMPipeline._prefetch_source_refs`
calls each resolver's own `_source_id` over the batch's rows before dispatching any
worker thread, so the prefetch's keys can never silently drift from what `resolve_one`
computes for the same row (a real risk flagged by `/gof-refactor-reviewer` before
writing any code — see the commit message). Chunked at 1000 ids per `IN()` clause
(`_SOURCE_REF_PREFETCH_BATCH_SIZE`) — a single unchunked query for `run_companies`'
observed ~73,691-row full-universe batch would exceed Postgres's per-query
bind-parameter ceiling.

**Concurrency interaction (question 2):** verified, not assumed, per the ticket's own
ask. The prefetch dict holds only primitive values (`(source_content_hash, entity_id)`
tuples, never `MdmSourceRef` ORM instances bound to the main-thread session it was
built on), built once before any worker thread starts, then threaded read-only into
every worker's own `ResolverContext` (`_resolve_row`/`_run_grouped_concurrent`'s
`_process_group`) — no worker ever mutates it or touches `self.session` for it.
Bundled onto `ResolverContext` itself (an optional `prefetched_source_refs` field)
rather than threaded as a new parameter through the three `resolve_one` signatures —
`/gof-refactor-reviewer`'s recommendation, since `ResolverContext` already exists
specifically to carry this exact shape of worker-scoped, read-only, built-once state.
Keyed on `(source_system, source_id)`, not `source_id` alone — the Spec review caught
that a source_id-only key would let `_skip_if_unchanged`'s fast path silently ignore
the `source_system` parameter it still accepts; every current caller only ever
prefetches one source_system per batch, so this was not an active bug, but nothing
enforced it either, and the pair-key closes the latent trap outright.

**Whether the win is worth it (question 3) — NOT independently measured, and this is
a real, acknowledged gap, not a silent skip.** This ticket's own text asked for real
wall-clock numbers before committing to the batching design, matching this map's
standing "real measurements, not estimates" preference. What shipped instead is
structural: 17 tests in `tests/mdm/test_skip_if_unchanged_bulk_prefetch.py`, including
round-trip-*count* regression guards proving `run_companies`/`run_persons`/
`run_securities`' `mdm_source_ref` SELECT count stays flat as row count grows (3 vs.
25 companies, 2 vs. 20 owners, 2 vs. 20 securities) instead of scaling with N. That
proves the round-trip *count* reduction is real and permanent; it does not prove a
materially faster wall-clock `mdm mastering` run at 16-way concurrency in live prod,
which is what the question actually asked. Getting that number requires a live
before/after comparison against real production Postgres (the same ~68ms
cross-region round-trip this map's own root-cause note already measured) — a fresh
deploy plus a full-universe `mdm mastering` run, which this session did not do.
**Follow-up needed:** capture a live wall-clock company/person/security-resolution
duration on the next prod deploy that includes this fix, and compare against the
2026-09-07 pre-fix baseline already on record (company resolution: 37.7 min for
73,691 rows, then 29.5 min on a rerun with more cached state) to confirm the
round-trip-count win actually translates into materially faster real-world runs, not
just fewer Postgres connections held open.

Tests: `tests/mdm/test_skip_if_unchanged_bulk_prefetch.py` (17 cases). Full `tests/mdm/`
suite (664+ tests) and full repo suite green, no behavior change for any caller that
doesn't opt in.
