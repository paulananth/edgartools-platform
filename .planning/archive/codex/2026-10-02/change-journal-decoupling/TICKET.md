# Decouple Change Journal

Owner: Codex. Status: implemented and qualified; review PR open. Claude has no assignment.
Branch: `codex/change-journal-decoupling-20261002`.
Base: `417147e8` (fetched main, 2026-10-02 11:58 ET).
Incorporated main `3934f967` (#785) before the full gate on 2026-10-02.

## Request and boundary

Check Change Journal against the loader-independent requirement and implement
the journal boundary. Journal stores and verifies durable event envelopes;
source interpretation, work execution and producer outbox recovery belong to
their owners. No deployment or history migration is authorized by this task.

## Checklist

- [x] Create an isolated branch and audit imports, runtime callers, skill and history — verified Company/SEC/MDM/Bookkeeping integrations inside the package plus generic store dependency on Bookkeeping config; inspected #738/#755/#757/#767; 2026-10-02 11:59 ET.
- [x] Extract shared envelope primitives without changing their behavior or migration checksums. — verified exact AST comparison for all four definitions, unchanged SQL, and affected PostgreSQL tests; 2026-10-02 12:32 ET.
- [x] Move acquisition, Rules authority, source evidence, MDM delivery and orchestration to owning modules; update executable callers without compatibility wrappers. — verified six integration AST comparisons, no stale executable import paths, 113 affected PostgreSQL tests; 2026-10-02 12:32 ET.
- [x] Separate standalone journal CLI from application-composed producer recovery while preserving existing warehouse command routes. — verified four architecture checks plus standalone wheel and existing CLI PostgreSQL checks; 2026-10-02 12:32 ET.
- [x] Update Change Journal skill to require journal-only operations and owner-controlled recovery; repair discovery if dangling. — verified Skill Creator validation, relative references, repaired discovery and idempotent link.sh; 2026-10-02 12:32 ET.
- [x] Add architectural and isolated-package tests that reject domain dependencies; run actual PostgreSQL 16 journal operations with restricted roles and no prerequisite skips. — verified four architecture tests, deliberate import fault, clean-wheel PostgreSQL acceptance; 2026-10-02 12:32 ET.
- [x] Build an independent wheel and qualify its exact contents and PostgreSQL operations in a clean environment without platform or parser dependencies. — verified 1 test passed in 114.22 s after bounding SQLAlchemy to 2.0; installed wheel initialized an empty store; 2026-10-02 12:32 ET.
- [x] Run affected source/control/MDM recovery tests and relevant full gate; record results and any remaining limitations. — verified 113 affected local tests; GitHub run 37034880553 passed all jobs and aggregate gate on code commit 49bcf9b6 (395 unit, 251 architecture, 491 MDM, 295 integration passed, 1 retained xfail, no skips); 2026-10-02 12:44 ET.
- [x] Document findings and verified implementation, commit/push and open a review PR. — verified published code commit 49bcf9b6, report/skill contracts and https://github.com/paulananth/edgartools-platform/pull/794; 2026-10-02 12:44 ET.

## Design review

The journal engine already exposes append/get/list/status/verify. The costly
coupling is placement/composition of producer code and reuse of Bookkeeping's
generic JSON/reference helpers. Extract shared primitives and move integrations
to their owners; retain existing algorithms and independent failure tests.
No new GoF class hierarchy is warranted. Domain workers may still use existing
Bookkeeping callbacks; decoupling Bookkeeping itself is separate PR #785 work.

## Qualification record

Main advanced to `8aecca6d` while testing; no owned-file overlap. GitHub tested
the PR merge with the current base. Full gate completed in 178 s, with 2 s from
run creation to the first job start. Independent wheel acceptance took 114.22 s
locally. The duplicate local integration run was interrupted after 17m25s once
the complete GitHub gate passed and the Mac was found nearly full; it recorded
180 passes, 1 retained xfail and the earlier, subsequently fixed wheel driver
failure. Its disposable container cleanup ran. No database prerequisite skips.

This follow-up changes qualification documentation only; its automatic CI run
is separate from the successful implementation gate cited above. No live
deployment, history migration, merge or Claude handoff occurred.
