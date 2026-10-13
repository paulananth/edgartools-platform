# SEC Company acquisition integration and bounded live qualification

Status: parked by the operator until the AWS Step Functions rollout,
2026-10-13 06:48 ET. Scope is prepared; integration and live proof are not
implemented. This is distinct from the completed offline capture slice.
No SEC data API request has been made in this task.

Owner: Codex, `codex/sec-company-live-qualification-20261013`, dedicated
worktree. Starting main: `a04bd29a`.

## Goal

Prove that a bounded, explicitly declared SEC Company submissions sample can
be acquired through the configured worker, independently verified, and consumed
through the existing Company route, with exact producer accounting and recovery
evidence. Publish the evidence and candidate source version for operator review.

## Scope and limits

- One feed: `sec.submissions.company/submissions`, JSON main documents and
  historical files derived only from independently verified main documents.
- Proposed live budget: at most five CIKs, 20 actual SEC HTTP requests including
  retries, one request per second, and explicit per-response byte bounds. The
  runner must enforce and qualify the request budget before live use. Exceeding
  any bound leaves the proof incomplete; no silent truncation or unbounded run.
- Freeze the exact source version, CIKs, rules/runtime digests, output namespace
  and initial request inventory. Continuation work is bounded, receipt-bound,
  idempotent and included in exact producer accounting.
- Use disposable local PostgreSQL 16 stores with restricted control, worker,
  verifier and Journal roles. Qualify an isolated namespace in existing dev S3
  once its account/bucket/prefix are identified and checked; production database
  writes, schedules, deployment and production source activation are out of scope.
- Existing pinned ticker and Name Frequency evidence remain inputs. This task
  does not add live ticker-catalog acquisition, company-facts or other feeds.
- Preserve raw HTTP entity bytes, hashes, configured parsing/output semantics,
  fencing, immutable storage and Journal/recovery contracts. Python handles
  HTTP/orchestration/evidence; Rust handles configured parsing/transformation;
  databases retain indexed retrieval and authoritative atomic/concurrency checks.
- Observe conditional HTTP behavior rather than promise a live 304. Record
  actual validators/statuses; retain offline 304/recovery coverage if the server
  supplies no usable validator or returns 200.

## Current evidence and reason

`docs/configured-capture.md` and the implemented `provider_capture.py` show
offline-qualified JSON capture with independent verification and durable-snapshot
recovery. The Company `capture` target still selects `artifact.copy`; capture
snapshots are not the receipt-bound raw-document input consumed by
`mdm/clean/raw_capture.py` and `company_prepare.py`. Capture completeness currently
proves presence/shape, not that a returned Company's CIK matches the requested
scope. Company/page identity, continuation handling, producer evidence and
capture-to-consumer wiring still need qualification.

The SEC API documentation confirms main submissions JSON and additional history
files named by the main response:
https://www.sec.gov/search-filings/edgar-application-programming-interfaces

The previous operator instruction held L8 and SEC requests waiting. The current
request assigns scoping/ownership to Codex. Prepare and qualify the integration
and exact bounded run package first; obtain the exact Rules approval required by
`rules/acquisition_authority.py` before live worker execution. Do not manufacture
operator approval or use a legacy/unauthorized fetch as a shortcut. Production
activation is separate from permission for a bounded qualification run.

## Operator sequencing decision

Operator, 2026-10-13: park this work until turning on AWS Step Functions.
The live proof should exercise the candidate deployed image, runtime roles,
artifact namespace and network path. Resume the parked integration prerequisites
as part of that rollout, run a bounded on-demand acquisition with verification
and recovery evidence, then enable unattended acquisition only after its exact
source/runtime and release gates pass. Step Functions orchestration does not
itself complete the capture-to-consumer or producer-accounting gaps above.

This decision defers the work; it does not mark acquisition ready or authorize
SEC requests, production activation or deployment now. The retired AWS rollout
script and passive infrastructure remain unchanged.

## Ownership

Claude is implementing L7 on `claude/issue20-l7-adapters`. Preserve his adapter,
mapdoc/catalog, contract migration, tests, onboarding and Issue 20 tracker edits.
Keep acquisition proposals in this workstream and add isolated worker/helper/test
paths. Shared operational Company source/configuration edits require ownership
reconciliation and the repository overlap guard; qualification freezes the
reconciled exact source version. Do not edit Claude's tracker to claim L8.

GoF review of the capture/Company interfaces and history: retain the registered
worker and public control seams. No provider hierarchy, controller callback or
parallel mutable recovery store is justified by this qualification task.

## Parts

- [ ] Publish this parking record as a reviewed PR; verify its scope/checklist and repository ownership before push. This is separate from the deferred implementation/proof PR below.
- [x] Inspect current main, PRs, worktrees and active L7 edits; establish isolated ownership. Verified git/GitHub readback and dedicated worktree, 2026-10-13 06:42 ET.
- [x] Review current capture, Rules authority, Company consumer interfaces and git history; define the integration gap. Verified code/docs and GoF review; current capture target is artifact.copy, 2026-10-13 06:42 ET.
- [x] Define bounded Company-only scope, architecture responsibilities and remaining approval boundary. Verified against current contracts and official SEC API documentation, 2026-10-13 06:42 ET.
- [x] Park remaining L8 work until AWS Step Functions rollout; retain it as an acquisition enablement gate. Verified operator instruction and updated status/checklist, 2026-10-13 06:48 ET.
- [ ] ~~Freeze sample selection and enforce/qualify the request, byte and continuation bounds before live execution~~ deferred to AWS Step Functions rollout / L8: operator sequencing decision.
- [ ] ~~Implement and independently verify capture-to-consumer receipt binding, configured CIK/file identity checks and bounded continuation orchestration~~ deferred to AWS Step Functions rollout / L8: required before acquisition enablement.
- [ ] ~~Produce exact acquisition manifest, producer counts, raw hashes and downstream Company input receipts; keep existing mastering semantics and pinned supporting inputs~~ deferred to AWS Step Functions rollout / L8: exact deployed-path proof.
- [ ] ~~Qualify public worker/verifier control and installed-bundle paths on real PostgreSQL 16; test Journal outage, corruption, lease takeover and lost acknowledgement offline~~ deferred to AWS Step Functions rollout / L8: qualify the candidate runtime.
- [ ] ~~Identify and verify isolated artifact destinations; prepare a reviewable run manifest and frozen candidate Rules version with its offline proof~~ deferred to AWS Step Functions rollout / L8: qualify the actual artifact destination.
- [ ] ~~Obtain exact operator Rules approval and resolve live-run authorization against the prepared request inventory and limits before SEC requests~~ deferred to AWS Step Functions rollout / L8: exact-version and bounded-run approval remains required.
- [ ] ~~Run the bounded live sample; record actual HTTP/continuation behavior, immutable artifact readback and independent checks; prove downstream consumption locally~~ deferred to AWS Step Functions rollout / L8: prove deployed acquisition before unattended runs.
- [ ] ~~Demonstrate durable-snapshot recovery without another GET; disclose any live behavior not exercised, retaining offline evidence separately~~ deferred to AWS Step Functions rollout / L8: qualify deployed recovery.
- [ ] ~~Review changes, verify affected commands/examples, guard/commit, PR and CI; publish proof and candidate source version. No go-live claim from a sampled proof~~ deferred to AWS Step Functions rollout / L8: publish the rollout's exact runtime/source evidence.
- [ ] ~~Production activation, deployment, schedules and full-universe capture~~ deferred to the operator's separate release decision after exact-version approval and go-live gates.

## Completion

This task completes only when implementation, installed/public-interface offline
qualification and the authorized bounded live proof have reproducible evidence.
An HTTP 200 alone, an offline fixture, or a plan is not completion. Any unchecked
part must remain visible and be reported as incomplete.
