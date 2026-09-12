# 05 — End-to-end verification

Type: task
Status: open

**Blocked by:** 04 — Step Functions wiring (needs a real deployed state
machine to run against).

## What to build

Deploy and verify in three steps, matching the plan's own Phase 4:

1. Deploy Ticket 01 (retirement fix) alone first; run a scoped
   repair/backfill against a real populated canonical copy to confirm
   retirement now publishes cleanly. No dependency on Tickets 02-04 for
   this to be independently verifiable.
2. Deploy Tickets 02-03 (checkpoint schema + refresh trigger) with unit
   tests green; no Step Functions change yet — verify via a manual
   `bootstrap-fundamentals` CLI invocation against a real CIK window that
   incremental scoping actually skips already-processed accessions/CIKs
   (already covered as acceptance criteria on those tickets — this step
   re-confirms it in combination, not each fix in isolation).
3. Deploy Ticket 04's Step Functions wiring; run a live `daily_incremental`
   execution and confirm:
   - `sec_earnings_release`/`sec_executive_record`/`sec_thirteenf_holding`
     gain new rows only for today's genuinely new filings (not a full
     re-parse).
   - `sec_financial_fact` gains new rows for CIKs with a new 10-K/10-Q and
     no `SemanticMergeConflictError` on publish.
   - Total added wall-clock time is bounded (not full-universe-scale).

## Acceptance

- [x] (waived) Step 1's live retirement-publish confirmation — the user
      explicitly declined live-AWS verification as unnecessary for closing
      Ticket 01 (see its own `## Answer`); test-level proof against a real
      `SilverDatabase`/DuckDB engine was accepted instead.
- [x] Step 2's live incremental-scoping confirmation recorded: per-filing
      run 1 processed 15 filings for CIK 908311, run 2 showed
      `filings_already_processed: 15, filings_parsed: 0`; entity-facts run
      1 fetched (`network_fetches: 1`), run 2 skipped (`silver_skips: 1,
      network_fetches: 0`). Confirmed twice — once against a throwaway
      verification task-def revision while diagnosing the read/write-path
      bugs (Tickets 17/18), then again against the real deployed prod task
      definition (`edgartools-prod-large:299`) after merging and deploying
      PR #603.
- [ ] Step 3's live `daily_incremental` execution confirmed clean, with
      row-count deltas for all four target tables and total added runtime
      reported. **Blocked on Ticket 04** (Step Functions wiring), which has
      not been started — nothing wires per-filing/thirteenf/entity-facts
      into `daily_incremental`'s actual Step Functions definition yet. All
      verification so far has been ad-hoc `bootstrap-fundamentals` ECS
      task invocations, not a real `daily_incremental` execution.
- [ ] This map's Destination is met — no code remains from the approved
      plan (`mossy-meandering-dream.md`) that isn't reflected in a
      resolved ticket here. **Not yet met**: Ticket 04 is the map's actual
      destination (bringing these modes into `daily_incremental`'s Step
      Functions pipeline) and remains open. Everything resolved so far
      (Tickets 01/02/03, plus duckdb-retirement-cutover 17/18) was
      necessary groundwork, not the destination itself.
