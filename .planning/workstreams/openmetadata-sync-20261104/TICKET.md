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
- [x] Read the post-reset, pre-publish inventory through the native API: 0 domains, glossaries, terms, database services, pipeline services, products and test cases; 25 built-in test definitions remain; no `Shared` domain (2026-11-04 21:05 EST).
- [x] Recheck the side-effect-free plan and independent read-only check before publish: 55 quality cases (50 checks, 5 fixes); zero domains and no `Shared`; check reported 216 differences, `publish: not_run`, and exit status 1 (2026-11-04 21:21 ET).
- [x] Load credentials privately and use the skill login flow; authenticated API readback verified `isAdmin=true`. The access token stayed in process memory and was not printed or saved (2026-11-04 21:43 ET).
- [x] Publish the configured Rules catalog: 480 write requests; publisher status `confirmed`, readback matched, 0 differences, 0 removals; created/updated counts remain unavailable. Independent `rules catalog check` returned `confirmed`, 0 differences, exit status 0 (2026-11-04 21:43 ET).
- [x] Independently compare native API inventories and associations with the current plan: domains/types, glossaries/domain links, terms, 18 table-domain memberships, 13 product table assets, 10 input ports, 22 glossary relations, 51 domain-to-table edges, and 31 pipeline-to-table edges all match; 30 table-lineage edges match the publisher readback (2026-11-04 21:48 ET).
- [x] Verify the execution boundary after publication: database and pipeline services have no connection config, ingestion-pipeline count is 0, and the latest-quality-results API returned HTTP 204 with no body (2026-11-04 21:48 ET).
- [x] Refresh the no-build fit report with post-publish evidence, current 2.0.2 execution boundary, and the remaining no-runner/no-Bookkeeping-integration limits; UI review remains unverified (2026-11-04 21:48 ET).
- [x] Run targeted publisher behavior tests: `tests/unit/test_rules_catalog.py` passed (45 tests in 43.59 seconds), covering publish rejection, partial write, remote drift and read-only confirmation (2026-11-04 21:22 ET).
- [x] Run the required documentation genericity lint after the OpenMetadata skill and report updates: `tests/unit/test_profiling_genericity.py` passed (93 tests, 2026-11-04 21:52 ET).
- [ ] Visually verify the end-user OpenMetadata UI; blocked by repository instructions prohibiting browser/GUI interaction, and API evidence cannot prove visual clarity.
- [ ] CI green on the updated PR head; keep the PR draft until publication evidence and CI are reviewed.
- [x] Learning → skill: documented private environment-based token refresh with an administrator check, full-instance reset boundaries, and the limit of publisher readback in `skills/openmetadata/SKILL.md` (2026-11-04 21:48 ET).
