# AutoOntology hosted sync

- [x] GoF consult: preserve the small lifecycle facade; use one configuration list and shared provisioning/verification functions. History: lifecycle introduced by PR 1782. {{now}}
- [x] Create dedicated readers through original private role files: all three connect with TLS and zero writable relations. {{now}}
- [x] Fix upstream placeholder model-key overrides; synthetic embedding probe passes. {{now}}
- [x] Import only three approved databases; native API and local embedding-store readback confirm 91 tables, 960 columns, 1051 embeddings. {{now}}
- [x] Verify denied DML for all three readers: DELETE WHERE false in explicit read-write transactions returns 42501; script regressions cover private shell parsing, reader reuse/target checks, model overrides and rejected privilege/TLS states. {{now}}
- [x] Standards: private values excluded, generic source list, least privileges and no source-data writes; Spec: only three approved sources, exact inventory/embedding readback; GoF: retain lifecycle facade, no additional pattern justified by history. {{now}}
- [ ] Publish validated scripts and skill in PR.
- [x] Learning → skill: source boundary, generic sync, private credentials, embedding preflight and readback. {{now}}

Runtime qualification used the sibling checkout at commit `8ff3060`; refreshed application containers without removing volumes. Semantic compilation and business-query qualification were not performed; catalog sync and stored embeddings are confirmed.

## Standards

Private URLs remain in mode-0600 local files. One JSON list drives all three sources. Dedicated readers have no administrative or write privileges; live denied-DML tests returned 42501 for every store. The CLI redacts driver failures at its outer boundary.

## Spec

Only MDM, RDM and Silver are configured and imported. API readback exactly matches source table/column inventories; persisted embedding counts match all imported tables and columns. The standard eight-key shared catalog remains intact.

## GoF

The existing lifecycle wrapper is a small facade introduced by PR 1782. No recurring variation justifies a class hierarchy or Strategy pattern. Configuration-driven functions keep provisioning and verification shared across the three stores.

Validation: 9 script regression cases; 109 genericity/guide-path checks; Ruff, shell syntax and diff whitespace checks pass. The psycopg test dependency is declared in the dev group and lockfile.
