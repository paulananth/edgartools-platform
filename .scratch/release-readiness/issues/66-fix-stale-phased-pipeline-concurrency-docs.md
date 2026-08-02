# Fix CLAUDE.md's stale Phased Pipeline concurrency documentation

Type: task
Status: open

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
