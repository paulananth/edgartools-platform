# 06-04 progress (partial) — EDGE-09/EDGE-11 skip-vs-miss disambiguation

Started 2026-07-12. **Incomplete** — paused on a recurring machine clock-skew (sleep drift breaks
AWS sigv4) + limited context. Durable finding below; clear next step for resume.

## Finding so far (from exec #2 = `load-history-06-1783560365`, the run that reached MdmExport)

exec #3 died in **Branch A** (bootstrap-next OOM building gold) **before** the fundamentals stages,
so it cannot disambiguate EDGE-09/11. exec #2 is the right probe — it failed later, at MdmExport.

Confirmed from exec #2 Step Functions history (`get-execution-history`):
- It **entered** `Stage1BEntityFacts`, `Stage1BPerFiling`, `Stage1BThirteenF`, then `MdmExport`
  (state-enter events present for all four) — so the per-filing and thirteenf fundamentals stages
  **did run**, they weren't unreachable.
- Multiple `TaskFailed` events are present in the same history.

**Interpretation (leaning, NOT yet nailed):** the per-filing/thirteenf stages ran and at least some
tasks **failed** → AD-13 `States.ALL` catch skipped them → `sec_executive_record` /
`sec_thirteenf_holding` left empty. This supports the **AD-13-skip** branch over **parser-miss** for
EDGE-09/11. **Not confirmed:** I could not correlate *which* `TaskFailed` id belongs to
`Stage1BPerFiling` vs `Stage1BThirteenF` vs `MdmExport` before the clock skew blocked further AWS
calls — so "each fundamentals stage failed" is not yet proven (the failures could be MdmExport's).

## Exact resume step (do this first next session)

1. Fix machine clock (`sudo sntp -sS time.apple.com`); re-verify `690` via `--profile edgartools-690`.
2. Correlate failures to stages in exec #2:
   `aws stepfunctions get-execution-history --profile edgartools-690 --region us-east-1 --execution-arn arn:aws:states:us-east-1:690839588395:execution:edgartools-dev-load-history:load-history-06-1783560365 --no-paginate`
   — order events by `id`; for each of `Stage1BPerFiling` / `Stage1BThirteenF`, check whether the
   next task-level event is `TaskFailed` (→ AD-13 skip, exit code / OOM in the ECS task logs) or
   `MapRunSucceeded` with 0 rows (→ parser miss).
3. If skip: pull the failed stage's ECS task log (`/aws/ecs/edgartools-dev-warehouse`,
   `warehouse-medium/...`) for the exit reason (expect exit 137 OOM, same class as exec #3 — which
   the committed `medium` 2→4 GB bump would address; deploy it before a fresh diagnostic load).
4. If parser-miss (stage clean, table 0): run `proxy_fundamentals.parse()` / `thirteenf.parse()` on
   one captured DEF 14A / 13F-HR info-table attachment locally to see if the parser returns [].

This distinguishes **Populate** (fix + re-run) from **Exclude** (documented source-coverage gap)
for EDGE-09 and EDGE-11 — the 06-04 deliverable.
