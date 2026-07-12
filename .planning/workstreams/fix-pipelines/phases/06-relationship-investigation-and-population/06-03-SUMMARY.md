---
phase: 06-relationship-investigation-and-population
plan: 03
status: complete
completed: 2026-07-12
---

# 06-03 Summary — Bounded load_history dev run + per-type coverage evidence

## Outcome

Task 3 (per-type artifact-coverage evidence for EDGE-09/10/11) is **complete**; it is the plan's
actual deliverable. Task 2's bounded `load_history` run was **attempted three times and did not
complete green** — execution #3 (`load-history-06-1783726338`) reached the Stage-3 gold build and
**OOM-failed** — but Stage-1 silver was captured, which is sufficient for the evidence per the
plan's "the load run is instrumental, not the deliverable" note. The OOM is root-caused and handed
to a separate hardening fix.

## Tasks

- **Task 1 — Coordination + readiness gate:** done earlier (`e62ed3e`). See doc Task 1 section.
- **Task 2 — Bounded load_history run:** exec #1 FAILED (INLINE Maps w/ ItemReader, fixed `e3c5fcb`);
  exec #2 FAILED after 10.6h (MdmExport MERGE targets unprovisioned, DDL fix `caa9964`); exec #3
  FAILED via **OOM (exit 137) building `sec_financial_fact` gold** in the 2 GB `edgartools-dev-medium`
  task → `States.ExceedToleratedFailureThreshold`. Full 5-whys in `06-03-LOAD-COVERAGE-EVIDENCE.md`.
  A green end-to-end run is **not** achieved; tracked as the OOM hardening follow-up.
- **Task 3 — Per-type coverage evidence:** **COMPLETE.** Read-only query of the canonical dev
  `silver.duckdb` + captured-filing form-type presence.

## Key result — all three EDGE types are ARTIFACT PRESENT, SILVER EMPTY (parser gaps)

| EDGE | Silver table | Artifact present | Silver rows | Class |
|------|--------------|------------------|-------------|-------|
| EDGE-09 EMPLOYED_BY | `sec_executive_record` | DEF 14A (11)+DEFA14A (12) | 0 | parser gap |
| EDGE-10 AUDITED_BY | `sec_accounting_flag` | companyfacts (2.7M `sec_financial_fact`) | 0 | parser gap |
| EDGE-11 INSTITUTIONAL_HOLDS | `sec_thirteenf_holding` | 13F-HR (61) | 0 | parser gap |

None are ARTIFACT MISSING (no fetch triage) and none are ready-to-populate. **Wave 3 (06-04/05/06)
is a parser/pipeline root-cause effort for each type**, not exclusion or fetchability work.

## Deviations from plan

- Task 2's completed green load was not achieved (OOM). Accepted per plan's instrumental-load
  note; evidence taken from captured Stage-1 silver instead. User-approved path ("both — shortcut
  now, fix after", 2026-07-12).
- Evidence source was a pulled `silver.duckdb` read-only query rather than the
  `edgartools-dev-mdm-counts` SM — both are sanctioned by the plan; the direct query gave silver
  table row counts the counts-SM does not expose.

## Follow-ups created

1. **OOM hardening (this session, "fix after"):** raise gold-stage task memory so `load_history`
   completes green at 150-CIK scale. See STATE / TODO.
2. **Wave 3 root-causes (06-04/05/06):** three fundamentals silver parsers not populating despite
   present artifacts — `sec_executive_record` (DEF 14A), `sec_accounting_flag` (companyfacts
   auditor fields), `sec_thirteenf_holding` (13F-HR).
