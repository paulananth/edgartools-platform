# Verify a Completed Load End to End

Type: task
Status: resolved
Blocked by: none
Blocks: 06, 07
Labels: wayfinder:task

## Question

Does one safely selected, already captured local load produce complete
Bookkeeping evidence that is admitted, published per load, and confirmed by
exact OpenMetadata readback?

## Checklist

- [x] Inspect local run and capture state read-only; select a suitable existing
  capture without requesting new provider data. Selected the Form 13F filings
  capture `p07-managers`: 10 already-captured submissions documents, no provider
  request. Its silver target lands one table with one registered check, and the
  source masters nothing, so the proof needs no MDM handoff (2026-11-09 21:52 ET).
- [x] Check shared-server activity and confirm the selected local run is safe
  before executing it. The shared server had other agents' runs still open and
  no live leases, so the load ran in an isolated store (`codex-quality-e2e`)
  rather than against shared data (2026-11-09 21:52 ET).
- [x] Verify per-unit outcomes are admitted and counted once. Run
  `16a1c10d-a797-4e09-ac66-84b2855b4cdd` completed in 0.3 min: 1 unit verified,
  168 rows checked, 0 failed, quality status passed (2026-11-09 21:52 ET).
- [x] Publish its native quality results and read back each exact timestamp,
  status, count and result detail. The result read back with timestamp
  `1794278458922` (2026-11-10T02:40:58.922Z, the receipt's observation time),
  status Success, 168 passed, 0 failed, and the result text names the run, the
  step, the unit and the observation time (2026-11-09 21:52 ET).
- [x] Confirm identical replay is idempotent and incomplete or failed
  publication remains explicit with nonzero status. Re-running the load loaded
  0 new documents; re-publishing sent 0 quality results and the result count
  stayed at 1 with the same timestamp. A nonexistent run returned exit 1
  ("quality evidence unavailable"); an unfinished run returned exit 1
  ("PENDING: not complete; 0/1 units verified and 1 unknown") (2026-11-09 21:52 ET).
- [x] Confirm `check` is read-only and record the run reference and evidence.
  `rules catalog check --bookkeeping-run` confirmed 1 of 1 quality result with
  its publish stage `not_run`, and the result count was unchanged afterward
  (2026-11-09 21:52 ET).
- [x] Learning → skill: `skills/data-operations/SKILL.md` → the per-load publish
  note now warns that `rules catalog publish` reconciles the whole catalog
  plan, so it must run from a checkout at current `origin/main` or it removes
  catalog objects the current rules describe (2026-11-09 21:52 ET).

## Answer

Yes. One already-captured load produced admitted version-2 quality evidence,
published per load, and confirmed by exact readback.

The load was the Form 13F filings capture `p07-managers` (10 submissions
documents, already on disk, no provider request) through the `silver` target.
The shared server had other agents' runs open, so the load ran in an isolated
store. The version-2 check was registered in a rules version saved only in that
store's Rules database and activated from draft — the source masters nothing,
so no proof or approval was needed — and the load ran with the quality gate
enabled. The production rules are unchanged: the feature stays disabled in
production pending the operator's enablement decision.

| Check | Result |
| --- | --- |
| Run | `16a1c10d-a797-4e09-ac66-84b2855b4cdd`, complete in 0.3 min |
| Admitted evidence | 1 unit verified, 168 rows checked, 0 failed, status passed |
| Readback | timestamp `1794278458922`, Success, 168 passed, 0 failed |
| Replay | 0 new documents loaded; 0 quality results re-sent; result count stayed 1 |
| Failed publication | nonexistent run: exit 1, "quality evidence unavailable" |
| Incomplete publication | unfinished run: exit 1, "PENDING: not complete; 0/1 verified" |
| `check` | read-only; confirmed 1 of 1; result count unchanged |

The result text read back names the run, the step `land`, the unit
`cf4e2a396efb79acff052574` and the observation time `2026-11-10T02:40:58.922Z`,
matching the receipt.

One operational lesson: `rules catalog publish` reconciles the whole catalog
plan, not only the quality results. Run from a checkout behind current main, it
removed catalog objects the current rules describe; republishing from current
main restored them. The quality results, keyed by timestamp, survived both. The
warning is now in `skills/data-operations/SKILL.md`.

## Remaining

- [ ] ~~Enable version-2 quality evidence in production rules.~~ Deferred to the
  operator's enablement decision: the proof shows the path works, but
  registering the check in a production source's rules and setting the gate in
  the shared environment is a switch-on the operator has not made.
- [ ] ~~Observe the published result in the shipped OpenMetadata UI.~~ Deferred
  to [Observe Per-Load History in the Shipped OpenMetadata UI](06-observe-history-in-shipped-openmetadata-ui.md);
  the result is published and waiting for the operator to view it.
