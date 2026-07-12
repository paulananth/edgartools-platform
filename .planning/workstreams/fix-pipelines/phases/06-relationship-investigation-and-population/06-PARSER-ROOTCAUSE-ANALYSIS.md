# 06 — Parser root-cause analysis (read-only) for EDGE-09/10/11

**Purpose:** ground Wave 3 planning (06-04/05/06). Task 3 (06-03) established all three EDGE
target tables are **ARTIFACT PRESENT, SILVER EMPTY**. This doc identifies *why* each stays empty,
read-only (code + pipeline wiring + silver inspection), so 06-04/05/06 fix the right thing.
No code changed. 2026-07-12.

## Pipeline wiring (confirmed) — all three modes ARE invoked

`load_history` Stage 1 runs, sequentially (all on `wh_medium_arn` = `edgartools-dev-medium`, 2 GB):

```
Stage1Parallel(WindowedBootstrap: bootstrap-next → ownership/ADV)
  → Stage1BEntityFacts   (bootstrap-fundamentals --mode entity-facts)
  → Stage1BPerFiling      (bootstrap-fundamentals --mode per-filing)
  → Stage1BThirteenF      (bootstrap-fundamentals --mode thirteenf)
  → MdmRun → … → gold-refresh
```

**Systemic finding (AD-13):** each Branch B stage has a `Catch` on `States.ALL` routing to the
*next* stage (`entity-facts→per-filing→thirteenf→MdmRun`). So **any fundamentals mode that fails
is silently skipped and the execution still succeeds** — the exact signature of "artifact present,
silver empty." Because all three run on the **2 GB `medium`** task (the same size that OOM-killed
exec #3's gold build), an OOM/failure in a fundamentals mode is a live, invisible possibility.
`deploy-aws-application.sh:1653,1711,1716` (the three catches).

## Per-type root cause

### EDGE-10 — `sec_accounting_flag` (AUDITED_BY) — most isolated lead (UNCONFIRMED)
- **Writer:** `silver_store.py:3220` INSERT; forensic/DEI fields per schema `silver_store.py:563-575`
  (`auditor_pcaob_id` ← `dei_AuditorFirmId`; forensic scores ← `accounting_flags.backfill_accounting_flags`, cross-period).
- **Evidence (soft — do not treat as settled):** the entity-facts stage *comment* (`deploy…:1665`)
  *claims* it writes `sec_financial_fact, sec_financial_derived, sec_accounting_flag`. In canonical
  silver: `sec_financial_fact`=2,729,147, `sec_financial_derived`=28,552, **`sec_accounting_flag`=0**.
- **Caveat (why this is a lead, not a conclusion):** these counts are from the **accumulated**
  canonical silver (many prior loads, last-modified 2026-07-10), so they **cannot** prove that a
  *single* entity-facts run wrote financial_fact-but-not-accounting_flag — the 2.7M could predate
  accounting_flag being wired, or come from a different code version. And "entity-facts writes
  accounting_flag" rests on a state-machine **comment**, not the verified entity-facts code path.
  So this is **not** confirmed to be a logic-gap-vs-AD-13-skip; it is the most *isolated* lead
  because its source (companyfacts) is demonstrably present and parseable.
- **Leading hypothesis (unconfirmed):** the DEI auditor-fact extraction (`dei_AuditorFirmId` →
  `auditor_pcaob_id`) and/or the cross-period `accounting_flags.backfill_accounting_flags` step is
  not actually invoked within entity-facts mode (or extracts nothing) — but a plain stage failure /
  never-invoked backfill is not yet ruled out. The 06-05 diagnostic below is the discriminator.
- **Next diagnostic (06-05):** trace the entity-facts code path in `bootstrap_fundamentals.py` →
  `accounting_flags.py`; confirm whether `backfill_accounting_flags` is called during entity-facts
  and whether `dei_AuditorFirmId` is present in the fetched companyfacts for a known 10-K filer.

### EDGE-09 — `sec_executive_record` (EMPLOYED_BY) — per-filing stage: skip-or-empty
- **Writer:** `silver_store.py:3274` INSERT; parser `parsers/proxy_fundamentals.py`
  (DEF 14A HTML → Summary Comp Table → rows; returns `{"sec_executive_record": []}` when no SCT found).
- **Evidence:** DEF 14A artifacts present (11 `DEF 14A` + 12 `DEFA14A` in `sec_filing_attachment`);
  `sec_executive_record`=0 **and** `sec_earnings_release`=0 (the other per-filing output) → the
  **whole per-filing stage produced nothing**.
- **Two live hypotheses (disambiguate in 06-04):**
  1. **AD-13 skip:** per-filing stage failed (OOM on 2 GB / error) and was caught → never wrote. Both
     per-filing tables being zero (not just one) points here.
  2. **Parser miss:** per-filing ran but `proxy_fundamentals` found no Summary Comp Table in the
     sampled DEF 14A docs (real returns-empty path at `proxy_fundamentals.py:84`).
- **Next diagnostic (06-04):** pull the Stage1BPerFiling child-execution status + its ECS task
  logs/exit code from a load run (look for exit 137 / caught failure); if it ran clean, feed one
  captured DEF 14A doc through `proxy_fundamentals.parse()` locally.

### EDGE-11 — `sec_thirteenf_holding` (INSTITUTIONAL_HOLDS) — thirteenf stage: skip-or-empty
- **Writer:** `silver_store.py:3303` INSERT; parser `parsers/thirteenf.py` (13F INFORMATION TABLE
  XML → rows).
- **Evidence:** 61 `13F-HR` filings in the captured feed; `sec_thirteenf_holding`=0.
- **Two live hypotheses (disambiguate in 06-04):**
  1. **AD-13 skip:** Stage1BThirteenF failed and was caught → never wrote.
  2. **Parser/attachment miss:** thirteenf ran but couldn't locate/parse the INFORMATION TABLE XML
     attachment for the captured 13F-HRs.
- **Next diagnostic (06-04):** Stage1BThirteenF child-execution status + logs; if clean, run
  `thirteenf.parse()` against one captured 13F-HR information-table attachment.

## Cross-cutting recommendations for Wave 3

1. **Fix the observability gap first (or alongside):** AD-13's silent `States.ALL` catch means
   Branch B failures never surface. Even after parser fixes, an empty fundamentals table will keep
   looking like "no data" instead of "stage failed." Consider surfacing per-mode
   rows-written/failure into the execution output or a status signal, so EDGE-09/10/11 can't
   silently regress. (Relates to the milestone's ARTF/observability items.)
2. **Sequencing vs. the OOM fix:** the three Branch B modes run on `medium`; the committed
   `medium` 2→4 GB bump (06-03) reduces the OOM-skip probability for EDGE-09/11 but does **not**
   address EDGE-10 (a logic gap, not memory). Deploy the memory fix before re-running a diagnostic
   load, so a fresh run's per-filing/thirteenf stages aren't skipped by OOM again.
3. **06-05 EDGE-10 note:** `accounting_flag` shares the fundamentals surface
   (`bootstrap_fundamentals.py`/`accounting_flags.py`) now consolidated under this workstream
   (ex-`fundamental-factors-v2`, unified Phase 10) — sequence EDGE-10 work with Phase 10 to avoid
   touching the same files twice.

## Classification for Wave 3 planning

| EDGE | Table | Root-cause class | Wave-3 disposition (likely) |
|------|-------|------------------|-----------------------------|
| EDGE-10 | `sec_accounting_flag` | Leading (unconfirmed): parser-logic gap vs. never-invoked backfill vs. skip — accumulated counts can't prove same-run; write asserted by a comment, not verified in code | **Diagnose first** (06-05), then likely populate — confirm the entity-facts→accounting_flag path before committing a fix |
| EDGE-09 | `sec_executive_record` | Stage skip **or** parser miss (disambiguate) | Populate if fixable; exclude only if SCT genuinely absent (06-04) |
| EDGE-11 | `sec_thirteenf_holding` | Stage skip **or** parser miss (disambiguate) | Populate if fixable; exclude only if info-table genuinely absent (06-04) |

No type currently looks like a true source-coverage exclusion — artifacts exist for all three;
the gaps are in parsing/pipeline, not fetchability.
