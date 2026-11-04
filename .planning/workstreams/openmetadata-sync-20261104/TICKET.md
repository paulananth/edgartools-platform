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

- [x] Rebase the sync branch onto `origin/main`; verified it is at `f1ed67045` with zero ahead/behind commits (2026-11-04 18:04 ET).
- [x] Reconcile the current Rules plan after rebase; `rules catalog plan --root rules` sent nothing and reports 8 domains, 8 glossaries, 22 terms, 66 assets, 2 quality definitions, 55 cases, 3 products, 21 pipelines and 134 lineage edges (2026-11-04 18:04 ET).
- [x] Confirmed the compose project owns `edgartools-catalog_db-data` and `edgartools-catalog_es-data`, each with one expected consumer; recorded the healthy 2.0.2 service state before reset (2026-11-04 18:06 EST).
- [x] Reset the local OpenMetadata instance with `docker compose down -v` for its own compose file; redeployed, verified both named volumes recreated, all three services healthy, and API version 2.0.2 (2026-11-04 18:10 EST).
- [ ] Make fresh API credentials available to the CLI process, then read back the post-reset catalog inventory without printing credentials; user reports loading them privately, but the worktree command environment reports both variables missing (2026-11-04 18:14 EST).
- [ ] Publish the configured Rules catalog through the supported CLI and verify publisher readback plus an independent read-only check, including no domain named `Shared`.
- [ ] Run required documentation checks and record sanitized reset, publish, and verification outcomes; publish this work on the branch with CI evidence.
- [x] Learning → skill: documented the full-instance reset boundary, exact volume ownership check, redeploy and health verification in `skills/openmetadata/SKILL.md`; required documentation checks passed (95 passed, 2026-11-04 18:10 EST).
