# Confirm Match Candidate-Prefetch Behavior Under Per-Window Batching

Type: research
Status: resolved

## Question

The map's grilling settled that resolution stays batch-shaped — one CIK
window's worth of parsed records resolved as a batch, immediately before
that window's silver commit — rather than per-row/streaming. `match.py`'s
matchers (`CIKExactMatcher`, fuzzy-name, Splink ML) score `attrs` against a
`candidates: list[dict]` parameter passed in by the caller, not by querying
Postgres themselves.

Confirm, by reading `pipeline.py`'s actual resolver-calling code (the
`CompanyResolver`/`PersonResolver`/`SecurityResolver` construction sites and
whatever builds their `candidates` list — `pipeline.py`'s own comments
mention "bulk prefetches... instead of two extra per-row silver
[queries]"): does today's full-universe-batch prefetch pull candidates from
MDM's *existing, already-resolved* Postgres population (i.e. is it correct
and cheap to re-run this prefetch once per window, since it's querying
Postgres — a separate, small, already-resolved dataset — not re-scanning
silver), or does it also depend on same-batch context in some way that a
smaller per-window batch would change (e.g. cross-references between rows
within the same batch, not just against the existing MDM population)?

Also check: is a fresh prefetch-per-window meaningfully more expensive than
today's one-time full-universe prefetch (N windows × prefetch cost vs. 1 ×
prefetch cost), and if so, by how much — is this a real performance concern
for [Decide the Coupling Mechanism Between MDM and Silver's Write
Path](02-decide-coupling-mechanism.md) to weigh, or negligible?

## Deliverable

An answer, with file:line citations: whether per-window batch resolution
changes match *correctness* (not just performance) versus today's
full-universe batch, and a rough cost estimate for the repeated-prefetch
question.

## Answer

**Structurally safe from a correctness standpoint, but not uniformly
cheap** — and the map's grounding note ("bulk prefetch... not per-row
lookups") turns out to overstate uniformity across entity types.

- **Company, Person (CIK-known path), Security**: never prefetch a
  candidate batch at all — each issues a live, indexed, per-row Postgres
  query (`resolvers/company.py:120-135`, `resolvers/person.py:112-132`,
  `resolvers/security.py:130-150`). Per-window batching changes nothing
  about their cost or correctness; there was no batch-level amortization
  to lose.
- **Adviser, Fund**: genuinely prefetch the *entire, unscoped*
  `MdmAdviser`/`MdmCompany`/`MdmFund`/`MdmSourceRef` tables once per call
  (`adv_bulk.py:190,201-205,321,327-335,336`), reused in-memory for every
  row in that call. Today MDM runs once for the whole ~62K-company
  universe (`pipeline.py:255`), so this happens once. Window size is 500
  CIKs (`warehouse_orchestrator.py:2694,6567`) → **~124 windows**. Moving
  to per-window resolution means ~124× more full-table scans, and because
  these tables grow monotonically across the run, cumulative cost is
  closer to O(N²/window_count) than O(N) — a real, not negligible,
  scaling concern. No live prod row counts were available to convert this
  into wall-clock numbers.
- **Structural gap, not just cost**: `run_advisers`/`run_funds`
  (`pipeline.py:424-432,660-668`) have **no CIK/window-scoping parameter
  at all**, unlike `run_companies`/`run_persons`. Their incoming-row query
  (`SELECT * FROM sec_adv_filing`, no `WHERE`) would need new scoping
  added before per-window resolution is even possible for these two
  types — this is a capability gap for [Decide Write-Path Command
  Scope](03-decide-write-path-command-scope.md) to account for, not a
  pure performance tradeoff.
- **Correctness**: confirmed no matcher in `match.py` holds state across
  calls or assumes a minimum/maximum candidate-list size (`Matcher`
  protocol, `:44-52`; `MatchPipeline.resolve`, `:202-212`) — a smaller
  per-window candidate pool is safe by construction. The one place batch
  shape matters is `adv_bulk.py`'s in-memory dedup dicts staying
  internally consistent *within* one call (already true regardless of
  batch size) — distinct from candidate-pool *incompleteness* from
  earlier windows not having run yet, which is real but is ticket 04's
  cold-start territory, not a bug here.
