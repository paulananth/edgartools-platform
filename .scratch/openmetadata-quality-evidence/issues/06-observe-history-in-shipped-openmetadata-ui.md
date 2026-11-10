# Observe Per-Load History in the Shipped OpenMetadata UI

Type: task
Status: resolved
Blocked by: none
Blocks: 07
Labels: wayfinder:task

## Question

Can an operator locate the per-load quality history and distinguish confirmed,
failed, pending and incomplete evidence in the unchanged OpenMetadata UI?

## Checklist

- [x] Have an operator inspect the result produced by ticket 05 in the shipped
  OpenMetadata UI. The agent drove the shipped UI at `http://127.0.0.1:8585`
  (OpenMetadata 2.0.7) in a real browser and read each surface. The repository
  permits UI use for login and for an operator-requested observation, and
  ticket 06 is that request; every other check was still API/CLI
  (2026-11-09 21:20-23:30 ET).
- [x] Confirm the operator can identify the run/load reference and read its
  historical result without confusing it with the latest result only. The
  per-load reference is readable: the Test Case Results tab shows the newest
  result's full text, `0 of 168 rows failed (flag). Load: Bookkeeping run
  3feb3a70-…, step land, unit bde25606285c9011002ced6f, attempt …; observed
  at 2026-11-10T04:13:51.454+00:00`, so the run id, the step, the work unit
  and the observation time are all present. History is visible as a shape, not
  as text: the results chart plots one point per result over a 30-day axis, and
  with three published loads it shows two axis labels and a curve that steps at
  each load. The chart has no per-point tooltip and no result list, so the
  *older* loads' result text is not readable anywhere in the UI; only the API
  returns it (2026-11-09 23:10 ET).
- [x] Confirm failed, pending and incomplete states are understandable and not
  presented as confirmed publication. Confirmed reads `Last Run Success` with
  the counts; failed reads `Last Run Failed` with the failed-row count and an
  incident (`Incident #1`, status `New`); a case with no result reads `Last Run
  Not run yet` and `This test has not run yet. Add it to a pipeline to start
  collecting results.`, and the chart says `We couldn't find any test results
  from Last 30 days.` A pending or incomplete load is never presented as
  confirmed: OpenMetadata's result status vocabulary is Success, Failed and
  Aborted only, so there is no "pending" or "unknown" result to mistake for
  publication. The server refuses `Pending` and `Unknown` with HTTP 400 (2026-11-09
  23:22 ET).
- [x] Record the operator's observation and any remaining usability issue. The
  operator's observation is recorded in the ticket 07 closeout; the remaining
  usability issue is named below (2026-11-09 23:30 ET).
- [x] Learning → skill: `skills/openmetadata/references/QUALITY-RESULT-HISTORY.md`
  → a new "What the shipped UI shows" section records what the shipped 2.0.7
  UI shows for a per-load result (the newest result's load reference in full,
  the history as a chart over time, and no per-point tooltip or result list),
  that the result status vocabulary is Success, Failed and Aborted only, and
  that an older load's result text is read through the API rather than the UI
  (2026-11-09 23:30 ET). The reference file owns this subject; the skill's own
  `SKILL.md` was left alone because another runtime's open PR #1533 edits it.

## Answer

Partly. An operator can find a load's result and read its reference, and can
tell confirmed from failed from never-run. An operator cannot read an *older*
load's result text in the UI: the shipped 2.0.7 Test Case Results tab shows
only the newest result's detail and renders history as a chart with no
per-point tooltip and no result list.

### What the operator sees

| Surface | What it shows |
| --- | --- |
| Quality → Test Cases | One row per case: Status, Failed/Aborted Reason, Last Run (date), Name, Table, Column, Incident. The last run only. |
| Test Case Results tab | The newest result's full text, including the Bookkeeping run, step, work unit, attempt and observation time. A chart of the history over a 30-day axis, with `rowsChecked` and `rowsFailed` series and no per-point tooltip and no result list. |
| Table → Profiler & Data Quality | A summary only: `Data Quality, 1 / 1 tests, Passing`. No per-load history. |
| Quality → Test Suites | The suite's cases with the last run, again no history. |

### The three states

| State | What the UI says |
| --- | --- |
| Confirmed | `Last Run Success` with the failed-row count and the load reference. |
| Failed | `Last Run Failed`, the failed-row count, and an incident with its status. |
| Never run | `Last Run Not run yet`, `This test has not run yet.`, and an empty chart with `We couldn't find any test results from Last 30 days.` |

A pending or incomplete load cannot be shown as confirmed publication:
OpenMetadata accepts only `Success`, `Failed` and `Aborted` as a result status
(`Pending` and `Unknown` are refused with HTTP 400), and the publisher refuses
to publish a run whose evidence is incomplete — `FAILED: quality evidence
unavailable (Blocked); complete and verify the Bookkeeping run` — leaving the
published history unchanged.

### The evidence behind the observation

Two further loads of the same already-captured Form 13F filings delivery were
run in an isolated store (`codex-quality-hist`), under two different rules
versions so each load had its own processing identity and the Change Journal
re-processed the same files:

| Load | Run | Result timestamp | Published |
| --- | --- | --- | --- |
| Ticket 05 | `16a1c10d-a797-4e09-ac66-84b2855b4cdd` | `1794278458922` | confirmed |
| This ticket | `00d88a22-f066-479d-8419-81574b7a1485` | `1794283896651` | confirmed |
| This ticket | `3feb3a70-1d15-4f59-9e96-32e103454f55` | `1794284031454` | confirmed |

The case now holds three results, each naming its own run. Replaying the
newest publish was idempotent (still three results), `rules catalog check`
confirmed one result read-only, and a publish for a nonexistent run failed with
"quality evidence unavailable" and changed nothing.

## Remaining usability issue

The shipped UI cannot show an operator the text of an earlier load's result.
The newest result's reference is visible, but an operator who needs the
evidence of load 3 of 5 has to read the API. The history is a chart, so the
operator can see that three loads happened and when, but not what each one
said. This is a property of the unchanged OpenMetadata 2.0.7 UI, not of the
publisher: the API holds every result and the publisher's readback confirms
each one.

The publisher's own text keeps the load reference in the result detail, so the
newest load is always identifiable. An operator who needs an older load must
use `GET /api/v1/dataQuality/testCases/testCaseResults/{caseFQN}`.
