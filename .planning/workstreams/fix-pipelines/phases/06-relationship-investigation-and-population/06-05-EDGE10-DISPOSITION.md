# 06-05 EDGE-10 (AUDITED_BY) Disposition

**Plan:** 06-05 (Wave 3, fix-pipelines)
**Status:** Task 1 complete (coordination gate). Task 2/3 pending operator approval on whether a
fresh entity-facts run is needed (see verdict below — current read is **no**, but this checkpoint
does not self-approve per the plan's `gate="blocking"`).

---

## Task 1: Coordination gate for any additional entity-facts fundamentals run

### 1. Is the entity-facts prerequisite already present in unified silver?

Source: `06-03-LOAD-COVERAGE-EVIDENCE.md`, Task 3 per-type coverage table (completed
2026-07-12, read-only query against the canonical dev silver
`s3://edgartools-dev-warehouse/warehouse/silver/sec/silver.duckdb`, 635 MiB,
last modified 2026-07-10T23:39Z):

| Signal | Value |
|---|---|
| `sec_financial_fact` rows (companyfacts entity-facts source) | **2,729,147** |
| `sec_financial_derived` rows (computed from the same entity-facts fetch) | **28,552** |
| `sec_accounting_flag.auditor_pcaob_id` rows (DEI-derived, EDGE-10's actual target) | **0** |

06-03's own classification for EDGE-10: **"ARTIFACT PRESENT, SILVER EMPTY"** — i.e. the
companyfacts entity-facts artifact for the loaded 150-CIK universe was fetched and successfully
parsed into `sec_financial_fact`/`sec_financial_derived` (2.7M + 28,552 rows prove the fetch and
the numeric-fact parsing path both ran and produced real rows), but the narrower DEI-auditor
subset of that same parse (`sec_accounting_flag.auditor_pcaob_id`, populated by
`parse_entity_facts` in `edgar_warehouse/parsers/financials.py` from the `dei` section of the
same companyfacts JSON) is at zero.

**Verdict: the entity-facts prerequisite IS present in the unified silver.duckdb.** This is not
the "entity-facts absent" branch the plan's Task 1 action anticipated (which would require a
fresh `bootstrap-fundamentals entity-facts` fetch run). Companyfacts data for this CIK universe
has already been fetched and parsed at least once (evidenced by the non-zero
`sec_financial_fact`/`sec_financial_derived` rows produced from that exact fetch).

### 2. Why no new fetch run is being requested right now

Two hypotheses remain open for *why* `sec_accounting_flag.auditor_pcaob_id` is 0 despite the
companyfacts fetch having succeeded, and neither one is decided by this checkpoint — that's
Task 2/3 root-cause work, done only after this gate clears:

1. **Parser/write-path gap** — something between `parse_entity_facts`'s DEI-derived
   `sec_accounting_flag` rows and `SilverDatabase.merge_accounting_flags` drops or fails to
   persist those rows even though the `dei` section of the fetched JSON contains
   `AuditorFirmId`/`AuditorName` facts.
2. **Genuine dei-absence for this specific 150-CIK universe** — `dei:AuditorFirmId` is a
   post-FY2021 HFCAA-driven DEI XBRL tag; if none of the 150 loaded CIKs' most recent annual
   filings in scope report it (e.g. small/foreign filers with delayed compliance, or the
   in-scope filings predate the requirement), zero accounting-flag rows would be the correct,
   non-buggy result for *this* universe, not a defect.

Both hypotheses are read against **already-fetched, already-parsed companyfacts data** that is
sitting in the unified silver.duckdb right now. Neither one requires re-fetching companyfacts
from SEC to investigate:
- Hypothesis 1 (parser/write-path gap) is fixed in code and verified by re-running the existing
  parser against the already-captured JSON (or by inspecting `merge_accounting_flags`/the DEI
  section directly) — no new SEC round-trip needed.
- Hypothesis 2 (genuine dei-absence) is falsified or confirmed by inspecting the same
  already-fetched JSON's `dei` section for the 150 CIKs — again no new fetch needed to check.
- Per DEC-009, re-running `bootstrap-fundamentals entity-facts` against the same CIKs would be a
  no-op fetch-wise in any case (idempotent skip of already-captured companyfacts), so it would
  not by itself produce new evidence about either hypothesis.

**Verdict: no new/additional entity-facts fetch run is needed as the immediate next step.**
The outcome is either (a) a parser/write-path fix applied to data already in unified silver
(Hypothesis 1, no fetch involved), or (b) a documented exclusion/finding that this universe's
DEI facts genuinely lack auditor tags (Hypothesis 2, also no fetch involved). Task 2/3 determine
which, without triggering a new `bootstrap-fundamentals entity-facts` run.

**Caveat (does not foreclose future coordination):** if Task 2/3's investigation instead shows
that the *fetched* companyfacts JSON for this 150-CIK universe never actually reached SEC's DEI
`AuditorFirmId` facts for a reason that would be fixed by re-fetching a differently-scoped or
larger universe (e.g. broadening beyond the 150-CIK D-02 bound, or the loaded universe skews to
filers whose annual filings predate FY2021), that would re-open the "is a fresh entity-facts run
needed" question and re-trigger this same coordination gate before any such run — this section
records the verdict for *now*, not a permanent closure of the coordination requirement.

### 3. Codex / `fundamental-factors-v2` coordination check (per CLAUDE.md / PROJECT.md standing caution)

Read `.planning/workstreams/fundamental-factors-v2/STATE.md` directly (not relying solely on the
orchestrator's framing) to confirm tombstone status independently:

- Frontmatter: `status: merged-into-fix-pipelines`, `merged_into: fix-pipelines`,
  `merged_date: "2026-07-11"`.
- `merged_note`: *"TOMBSTONE — consolidated into fix-pipelines on 2026-07-11 (Codex->Claude
  hand-off, user-authorized). Completed Phases 1-2 remain here as history. Outstanding Phase 3
  (cash-conversion-cycle) was grafted to fix-pipelines as unified Phase 10. Do NOT resume this
  workstream separately — see .planning/workstreams/fix-pipelines/ROADMAP.md."*
- Confirmed via `git branch -r | grep -i codex` — no remote branches matching `codex`. No
  `codex/fundamental-factors-v2` ref exists.
- `fix-pipelines/STATE.md` "Active Decisions" still carries the older standing caution text
  ("AUDITED_BY (EDGE-10) ... must coordinate with the active `fundamental-factors-v2` workstream
  (Codex)") — this predates the 2026-07-11 consolidation and is now superseded by the tombstone;
  not updated to reflect the merge as of this check (a documentation-lag observation, not a
  blocker).

**Conclusion: `fundamental-factors-v2` (Codex) is not an active, separate workstream.** It was
consolidated into `fix-pipelines` itself on 2026-07-11 (unified Phase 10, Codex→Claude
hand-off). There is no independent Codex runtime or branch that a fresh fundamentals run could
collide with — the "coordinate before running fundamentals in dev" constraint is now (per
06-03's own EDGE-10 coordination note, carried forward from 06-CONTEXT.md) an intra-workstream
sequencing concern, not a cross-runtime one. Combined with the Section 2 verdict (no new fetch
run is needed right now), this coordination check is moot for the immediate next step — but is
recorded here in case Task 2/3's investigation reopens the "is a fetch run needed" question per
the Section 2 caveat.

### 4. In-flight dev execution check (DEC-009 / no `--force`)

No entity-facts fetch run is planned as the immediate next step (Section 2), so there is no
run to check for overlap against right now. If Task 2/3 later determines a fresh
`bootstrap-fundamentals entity-facts` run is required after all (Section 2 caveat), that run
must (a) re-verify no `RUNNING` dev execution exists first (same check pattern 06-03 Task 1
used: `aws stepfunctions list-executions --status-filter RUNNING`) and (b) never pass `--force`
per DEC-009 (SEC data idempotency — already-captured companyfacts artifacts must be skipped by
default).

---

## Coordination outcome summary

| Check | Result |
|---|---|
| Entity-facts prerequisite present in unified silver | **YES** — `sec_financial_fact` (2,729,147 rows) and `sec_financial_derived` (28,552 rows) prove the companyfacts fetch+parse already ran for this universe |
| Is a fresh/additional entity-facts fetch run needed right now | **NO** — root-causing the `sec_accounting_flag.auditor_pcaob_id`=0 gap (parser/write-path vs. genuine dei-absence) does not require re-fetching; DEC-009 makes a same-universe re-fetch a no-op regardless |
| `fundamental-factors-v2` (Codex) active/in-flight, could a run overlap | **N/A / moot** — tombstoned into this same workstream 2026-07-11; no separate Codex branch or runtime exists (`git branch -r` confirms) |
| DEC-009 (no `--force`) honored | **N/A for now** (no run planned); recorded as a hard requirement if Section 2's caveat later triggers a run |

**This checkpoint does not self-approve.** Per the plan's `gate="blocking"` on Task 1, execution
stops here for explicit operator sign-off before Task 2 (parser/data root-cause work) proceeds.
See `<resume-signal>` in `06-05-PLAN.md`: type "approved" (no entity-facts fetch run needed;
proceed to Task 2's parser/data root-cause investigation against existing unified silver) or
describe a coordination blocker.

### Observation (out of scope for this checkpoint, flagged for the operator)

`fix-pipelines/REQUIREMENTS.md`'s traceability table (lines ~100-102) already marks EDGE-09,
EDGE-10, and EDGE-11 as **"Complete"** for Phase 6, and the requirement bullets themselves
(lines 43-45) are checked `[x]` — despite `fix-pipelines/STATE.md` recording that Phase 6 is
still executing (plan 3 of 6, 06-04 not yet started at the time this doc was written, 06-05 not
yet approved past Task 1). This looks like a premature status update, most likely introduced
during the 2026-07-11 consolidation commit (`618049e`) rather than anything from this plan's
execution. Not corrected here — REQUIREMENTS.md is a shared orchestrator-owned artifact and this
worktree agent is stopping at a checkpoint, not completing the plan.
