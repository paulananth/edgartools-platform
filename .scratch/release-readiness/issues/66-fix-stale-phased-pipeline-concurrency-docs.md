# Fix CLAUDE.md's stale Phased Pipeline concurrency documentation

Type: task
Status: resolved

## Question

CLAUDE.md's "Phased Pipeline" section documents `load_history` as running
`seed-universe → bootstrap-batch ×N (MaxConcurrency=10)`, and its "Key invariants" section
separately says `BOOTSTRAP_BATCH_CONCURRENCY` defaults to 3 (recommended range 2-5). Neither
figure describes what's actually deployed for the pipeline operators use.

Found live while answering a throughput question (2026-08-02), checked directly against AWS,
not assumed from the doc:

- `aws stepfunctions describe-state-machine --state-machine-arn
  arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-prod-load-history` — the state
  machine has **no** `bootstrap-batch ×N` Map at all anymore. It's structured as
  `Stage0CompanyIdentity`, `Stage1Parallel/WindowedBootstrap`, `Stage1BEntityFacts`,
  `Stage1BPerFiling`, `Stage1BThirteenF` — five separate Distributed Maps, **every one
  `MaxConcurrency=1`**, confirmed by their own in-definition `Comment` fields ("one window at a
  time so silver/ownership/ is consistent"). This is deliberate (same class of reason as the
  earlier-documented ticket-20 N-way silver-promotion-race finding elsewhere in CLAUDE.md), not
  an oversight — but it means `load_history` runs fully sequential today, not parallel.
- A genuinely separate, standalone state machine, `edgartools-prod-bootstrap-batched`
  (`infra/scripts/deploy-aws-application.sh`'s `write_bootstrap_batched_definition`), does have
  a `BatchBootstrap` Map at `MaxConcurrency=3` (matching the deploy script's
  `BOOTSTRAP_BATCH_CONCURRENCY` default — this is where CLAUDE.md's "Key invariants" `3`/`2-5`
  figures actually apply). But `aws stepfunctions list-executions` on it returns **zero
  executions ever** — it is live, deployed infrastructure that has never actually run in prod.
- The "~15 min for 100 companies (vs 30-90 min sequential)" timing claim in the Phased
  Pipeline section was almost certainly measured against an older architecture, before
  `load_history` was restructured into the current `MaxConcurrency=1` windowed shape. It does
  not describe current deployed throughput and is actively misleading for anyone estimating
  how long a `load_history` run will take today.

## Required work

- Rewrite CLAUDE.md's "Phased Pipeline" section's Stage 1 description to match the live
  `edgartools-prod-load-history` definition: `Stage0CompanyIdentity` →
  `Stage1Parallel/WindowedBootstrap` → `Stage1BEntityFacts`/`Stage1BPerFiling`/
  `Stage1BThirteenF`, all `MaxConcurrency=1`, windowed/sequential by design.
- Either remove the "~15 min for 100 companies" timing claim or replace it with a
  freshly-measured figure against the current sequential shape — do not carry forward an
  unverified number from a different architecture.
- Clarify in the "Key invariants" section that `BOOTSTRAP_BATCH_CONCURRENCY`/`MaxConcurrency=3`
  applies to the standalone `bootstrap-batched` state machine, not to `load_history`'s internal
  Maps (which are hardcoded to 1, not controlled by that env var at all) — and flag that
  `bootstrap-batched` has zero prod executions, so document it as unused/unverified rather than
  as an active throughput lever until someone actually runs it.
- Spot-check whether any other CLAUDE.md sections (e.g. "Do NOT run `bootstrap-next` locally
  for large batches" reasoning, or the BOOTSTRAP_BATCH_CONCURRENCY recommended-range guidance)
  implicitly assume the old `bootstrap-batch ×N` shape and need the same correction.

## Done when

CLAUDE.md's Phased Pipeline and Key invariants sections match the live AWS state machine
definitions (re-verified via `describe-state-machine`, not re-copied from memory), and no
remaining sentence in CLAUDE.md implies `load_history` runs CIK batches in parallel.

## Resolved (2026-08-04)

Re-verified every claim live against AWS immediately before writing (not from this ticket's
2026-08-02 findings, which could themselves have drifted): `edgartools-prod-load-history`'s
Map states (`Stage0CompanyIdentity`, `Stage1Parallel/WindowedBootstrap`, `Stage1BEntityFacts`,
`Stage1BPerFiling`, `Stage1BThirteenF`) are all still `MaxConcurrency=1`; `WindowedBootstrap`'s
task command is `bootstrap-next --silver-only` (not `bootstrap-batch` at all);
`edgartools-prod-bootstrap-batched` still exists at `MaxConcurrency=3` with zero executions
ever; `edgartools-prod-silver-mdm-gold`'s `BatchSilver` Map is the pipeline the
`BOOTSTRAP_BATCH_CONCURRENCY`/`bootstrap-batch` invariants actually govern (confirmed its task
command is literally `bootstrap-batch --artifact-policy skip --parser-policy skip`, matching the
existing invariant bullets exactly).

Rewrote CLAUDE.md's "Phased Pipeline" section: Stage 1 diagram now matches the live 5-stage
shape (Stage 0/1/1B/2/3), explicitly notes `MaxConcurrency=1` throughout Stage 1/1B with the
real reason (ticket-20-class silver-promotion-race avoidance), and separately documents the two
genuinely-parallel pipelines (`bootstrap-batched`, unverified/unused; `silver-mdm-gold`, real
and live) so a reader can't conflate either with `load_history`. Removed the unverified "~15 min
for 100 companies" timing claim (no fresh measurement exists for the current sequential shape;
per the ticket's own instruction, did not fabricate a replacement number). Reworded "Do NOT run
`bootstrap-next` locally" to the actual current reason (resumability/retry/correct sequencing/
the sec_fetch_active lease), since the old "throughput" framing no longer holds now that
`load_history`'s own Stage 1 is also `MaxConcurrency=1`. Added a preamble to "Key invariants"
clarifying which two pipelines the `bootstrap-batch`/`BOOTSTRAP_BATCH_CONCURRENCY` bullets
actually apply to. Spot-checked the rest of CLAUDE.md for the same stale assumption (grep for
`bootstrap-batch`/`MaxConcurrency`/`N×10`/`parallel`) — no other section carries it.
