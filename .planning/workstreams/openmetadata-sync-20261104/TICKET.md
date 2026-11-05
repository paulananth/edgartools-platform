# Sync the configured catalog to local OpenMetadata

## Scope

Use the current Rules configuration as the source of truth and local
OpenMetadata as the destination. The operator now requests a full local
instance reset and redeploy before publishing the configured catalog. This
deletes only the `edgartools-catalog_db-data` and `edgartools-catalog_es-data`
volumes owned by `infra/openmetadata/docker-compose.yml`; do not touch other
projects' resources. Do not run source requests, source processing, or data
pipelines.

## Checklist

- [x] Rebase the sync branch onto current `origin/main` after fetching; `HEAD` now has `origin/main` as its parent (2026-11-04 21:21 ET).
- [x] Reconcile the current Rules plan after rebase; `rules catalog plan --root rules` sent nothing and reports 8 domains, 8 glossaries, 22 terms, 66 assets, 2 quality definitions, 55 cases, 3 products, 21 pipelines and 134 lineage edges (2026-11-04 18:04 ET).
- [x] Confirmed the compose project owns `edgartools-catalog_db-data` and `edgartools-catalog_es-data`, each with one expected consumer; recorded the healthy 2.0.2 service state before reset (2026-11-04 18:06 EST).
- [x] Reset the local OpenMetadata instance with `docker compose down -v` for its own compose file; redeployed, verified both named volumes recreated, all three services healthy, and API version 2.0.2 (2026-11-04 18:10 EST).
- [x] Read the post-reset inventory through the native API: 0 domains, glossaries, terms, database services, pipeline services, products and test cases; 25 built-in test definitions remain; no `Shared` domain (2026-11-04 21:05 EST).
- [x] Recheck the side-effect-free plan and independent read-only check: 55 quality cases (50 checks, 5 fixes); zero domains and no `Shared`; check reports 216 differences, `publish: not_run`, and exit status 1 (2026-11-04 21:21 ET).
- [ ] Load a write-capable token privately. The current token reads successfully but has only `BotImpersonationRole` and `DefaultBotRole`, with no Admin role; the first publish returned HTTP 403 before any write request completed (2026-11-04 21:05 EST).
- [x] Refresh the no-build fit report with the full-reset inventory, 55-case plan, 216 readback differences, current 2.0.2 trigger distinction, and verified absence of an OpenMetadata integration in Bookkeeping/workers; the no-go remains and visual UI review is unverified (2026-11-04 21:22 ET).
- [x] Run targeted publisher behavior tests: `tests/unit/test_rules_catalog.py` passed (45 tests in 43.59 seconds), covering publish rejection, partial write, remote drift and read-only confirmation (2026-11-04 21:22 ET).
- [x] Run the required documentation genericity lint: `tests/unit/test_profiling_genericity.py` passed (93 tests) (2026-11-04 21:22 ET).
- [ ] ~~Visually verify the end-user OpenMetadata UI~~ deferred: repository instructions prohibit browser/GUI interaction; API evidence cannot prove visual clarity.
- [ ] Publish the configured Rules catalog through the supported CLI and verify publisher readback plus an independent read-only check, including no domain named `Shared`.
- [ ] Run required documentation checks and record sanitized reset, publish, and verification outcomes; publish this work on the branch with CI evidence.
- [x] Learning → skill: documented the full-instance reset boundary, exact volume ownership check, redeploy and health verification in `skills/openmetadata/SKILL.md`; required documentation checks passed (95 passed, 2026-11-04 18:10 EST).
