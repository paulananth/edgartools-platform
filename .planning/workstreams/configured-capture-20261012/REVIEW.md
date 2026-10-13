# Configured capture review

Baseline: rebased main `2e78dc12`; final capture implementation `43a3c34e` (formerly `599f23c4` before the rebase).
Scope: isolated configured HTTPS JSON worker/verifier and unused SEC client
retirement. No provider request, source activation, or deployment.

## Standards

Initial P2: the Journal SPEC claimed a retired Bookkeeping authorization-intent
hook. Corrected to public frozen-task/live-lease renewal, Journal append/readback,
and immediate renewal before GET, with separate transaction boundaries and
logical effect keys. Reviewer confirmed resolution; no substantive findings remain.

## Spec

Independent read-only review found no actionable in-scope defect. Frozen
bindings, mandatory provider lease, acknowledged Journal intent, bounded/no-
redirect GET, immutable snapshot, 304 authenticated direct-200 reuse, and
independent verification match the approved isolated-slice contract.
Plan completion audit: 9/9 substantive in-scope items done; publication/CI passed; PR #933 merged. Explicitly deferred integration work stays unchecked in TICKET.

## GoF and pre-landing review

Leave the existing function/worker seams. SEC client history changed for rate,
conditional fetching and authority (`e0296294`, `daff76b2`, `ad43cfac`); it has
no surviving executable callers. A provider hierarchy would add indirection
without a present second implementation. Keep HTTP transport separate from
receipt orchestration, retain immutable Artifacts and the public control facade.
Root review of SQL/data safety, race/fence boundaries, URL authorization, typed
bounds and profile dispatch found no remaining defect. No SQL domain hook or
new mutable control store was introduced.

## Coverage

AI-assessed coverage is 30/30 selected significant behavioral paths, not measured
line coverage or an exhaustive claim. Audit added 19 snapshot/frame/storage
checks; parent added 6 restricted PG16 cases for missing provider leases,
post-GET lease loss/recovery, and verifier rejection of missing/changed evidence.
The strengthened hash-consistent forged candidate case also passed separately.

## Evidence

- All Rust acceptance tests passed, including two new presence tests.
- 58 initial capture checks, runtime pinning check, 19 frame/storage cases and
  six added PG16 recovery cases and six page/unsupported-configuration cases passed: 90 distinct targeted cases before the final pre-HTTP configuration regression across these runs.
- Unit/architecture: 990 passed (4m25s), before the 19-case audit addition.
- Maintained PG16 control after rebase: 49 passed (1m48s).
- Installed committed wheels, actual capture/public verifier and whole-package
  import/ownership: 2 passed (5m38s); no checkout or domain libraries.
- Public workers help/describe and documentation examples verified.
- Caller inventory and overlap guard passed; foreign worktrees untouched.

Adapter/fallback retirement waits for Claude's changed-document selection
interface. Company manifest retirement, continuation producer integration and
live SEC/Rules qualification are still pending; this slice is not go-live proof.

No VERSION/CHANGELOG pipeline exists here. Packages remain their existing
0.1.0 and install by pinned git ref. Unrelated historical TODOS organization and
foreign tracker/skill files were not rewritten.

Documentation follow-up: Company acquisition status/recovery wording and README capture link now match the qualified worker; genuine page selection and all four unsupported approved formats plus oversize bound were verified before HTTP.

Final delta: a red PG16 regression reproduced a GET before a natively invalid approved configuration was rejected. The shared native builder now compiles in `_load` before effects and remains the payload checker afterward. Standards, Spec and GoF reviewers confirmed the fix. Final capture and genericity suite: 150 passed (91 capture cases plus 59 genericity checks, 2m37s). Initial CI identified only source-specific names outside Journal SPEC examples; generic wording corrected and verified. Installed final capture wheels at `599f23c4`: 2 passed in 5m55s. All six required CI checks passed at that commit. The rebase preserved capture runtime files exactly; combined-state CI passed all six required checks at `43a3c34e` (run `38334540421`). PR #933 merged as `0e5db242` on 2026-10-12 22:02 ET.

Qualification record closure: live GitHub readback on 2026-10-13 06:16 ET confirms the merged PR and its exact green head. No runtime changes in this record. Remaining adapter/fallback, Company manifest and live-source qualification are explicit deferred items. The changed-document speed-ups were separately deferred by the operator in #934; their deferral does not invalidate the capture qualification.
