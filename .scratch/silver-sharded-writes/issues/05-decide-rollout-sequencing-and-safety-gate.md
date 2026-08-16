# Decide Rollout Sequencing and Safety Gate

Type: grilling
Status: resolved
Blocked by: 01, 02, 03, 07

## Question

Which primary command/surface pilots the sharded write path first —
`load_history`'s `WindowedBootstrap` (biggest blast radius, but also the
biggest OOM/cost benefit since it's the full-universe backfill),
`load_history`'s Stage 1B `bootstrap_fundamentals.py` writer (ticket 07's
"fourth surface" — same windowing shape as `WindowedBootstrap`, and the
same commands already patched once this session for the `ToleratedFailurePercentage`
gap), `daily_incremental` (runs continuously, so any benefit or any bug
compounds daily), or `bootstrap` (smallest scope, likely lowest risk to
pilot on)? And what verification
must pass before flipping any of them onto the shard path in prod — this
repo has documented history (CLAUDE.md's "INSTITUTIONAL_HOLDS/EMPLOYED_BY"
and "Manifest-pipeline ownership + cursor-syntax incident" 5-whys) of
subtle correctness regressions from getting sharding/concurrency
assumptions wrong. Consider: a dry-run/shadow mode that writes shards
alongside the existing monolith and diffs the two before trusting shard
output as canonical? A parity check against one real production run?
Something else?

## Deliverable

A decision: rollout order across the three commands, and the specific
verification gate (steps, not just "test it") each must pass before its
shard-path flip goes live.

## Answer

**This ticket's grilling session also settled a map-level scope decision**
(recorded here since it surfaced here; the map's Destination/Out-of-scope
sections carry the full detail — "Scope correction #2"): `daily_incremental`
and `bootstrap` are **removed from this map's destination**. Once tickets
01/02/03/07 made each surface's real cost concrete, the honest comparison
was: `WindowedBootstrap`/`bootstrap_fundamentals.py` are proven-pattern,
moderate-effort, and are exactly the two surfaces that caused both live
incidents this effort started from; `daily_incremental`/`bootstrap` need
genuinely new multi-shard-write engineering that doesn't exist anywhere in
this codebase. "Aiming to act soon" favors shipping the safe, high-value
slice now over solving the hardest 20% before shipping anything.
`daily_incremental`/`bootstrap` remain a legitimate future map, not
abandoned — see "Out of scope" on the map.

**1. Pilot order:** `WindowedBootstrap` and `bootstrap_fundamentals.py`'s
three modes ship together, as one coordinated change, not staggered. Both
share the identical fix shape (wire CIK resolution to read the
already-written `cik_snapshot.jsonl` before DB-open, instead of re-querying
an already-open DB — tickets 01 and 07), and with `daily_incremental`/
`bootstrap` now out of scope, these two surfaces *are* the whole remaining
destination — there's no smaller subset to sequence ahead of the other.

**2. Risky-table handling:** narrowing scope also narrowed the correctness
risk. Of ticket 03's flagged tables, only two are actually written by these
two surfaces: `sec_raw_object` (content-hash key, written by both via the
shared `bronze_filing_artifacts.py` pipeline) and `sec_company_filing`
(multi-registrant accession risk, written by `WindowedBootstrap`).
Everything else ticket 03 flagged is out of scope for this narrower
destination — `pipeline_run_lease` belongs to Daily Identity Refresh
(`daily_incremental`/`bootstrap`'s stage, now out of scope itself); the ADV
tables belong to the separate `FetchAdvBulk` pipeline; `sec_subsidiary_evidence`/
`sec_auditor_report_evidence` have no confirmed caller in the codebase
today. **Decision: full replication for `sec_raw_object` and
`sec_company_filing`** — same treatment as the existing ADV global tables.
Both are small relative to the CIK-scoped tables actually driving the
1.5GB size, so duplication cost is minor; this removes the correctness risk
entirely rather than working around it, and automatically resolves the
three dependent tables that inherit `sec_company_filing`'s resolution
(`sec_ownership_reporting_owner`, `sec_employment_event`,
`sec_thirteenf_filing`) — no separate decision needed for them.

**3. Monolith retention:** migrate every consumer first, then cut over
cleanly — not dual-write. Ticket 02's full consumer list (gold-refresh and
all of `GOLD_AFFECTING_COMMANDS`, `validate_data_quality.py`,
`verify_pipeline_run.py`, 5 ops scripts) must be moved onto
`ShardedSilverReader`-based reads (or gold-refresh's separate
bookkeeping-write redesign, per ticket 02) before `WindowedBootstrap`/
`bootstrap_fundamentals.py` stop writing the monolith. More work up front
than dual-write, but the platform never runs two storage representations
simultaneously, and avoids the failure mode ticket 02 flagged: the 5 ops
scripts would silently serve stale data with no error signal if the
monolith stopped being updated while they still read it directly.

**4. Safety gate:** shadow/dry-run mode with N consecutive clean diffs.
Write shards alongside the existing monolith merge for N real production
`load_history` runs, diff the two outputs row-for-row, only cut the
monolith write off after N consecutive clean diffs. Matches this repo's
existing "verify before trust" pattern (`migrate_silver_shards.py`'s own
3-layer verification: row-count parity, CIK-set parity, SHA-256
checksums) — reuse that same verification machinery rather than building
new diff tooling from scratch. `N` itself (and what "clean" tolerates, if
anything, for the two full-replication tables) is left to the
implementation session, not decided here.
