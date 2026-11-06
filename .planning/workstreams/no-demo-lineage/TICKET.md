# Exclude OpenMetadata's default AI lineage

Operator: "lineage is not correct remove ai related lineage and never insert
it back"; clarified "there are two default liniage created by open metadata".
The installed release seeds two demo services and eleven example edges.
Real source, pipeline, domain and business relationships are outside this removal.

- [x] Verify two bundled seed service groups and eleven exact edges against
  the live native inventory (2026-11-06 07:20 ET).
- [x] Configure the read-only empty seed override. The installed release's
  actual CommonUtil resource discovery/loader resolved it as [] with the
  matching classpath precedence; compose validates (2026-11-06 07:20 ET).
- [x] Delete eleven exact demo edges through native APIs; repeated native
  reads find zero. No assets deleted (2026-11-06 07:20 ET).
- [x] Recreate only the catalog server: healthy with the read-only override;
  PostgreSQL/search container identities unchanged. Native readback confirms
  zero demo edges after startup and all 85 real platform edges exactly
  unchanged (2026-11-06 07:25 ET). Docker's first stop confirmation failed;
  retrying the now-stopped target server succeeded without engine maintenance.
- [x] Review Standards, Spec and GoF: no implementation findings; clarify the
  skill's local enforcement scope. All 98 genericity/path checks and compose
  validation pass (2026-11-06 07:20 ET).
- [x] Publish ready PR #1453; final configuration passes compose validation
  and 98 file-only checks, with native restart proof above
  (2026-11-06 07:31 ET). CI and merge are recorded on the PR.
- [x] Remove exactly the two named demo services and their attached sample
  children from the active catalog. Post-restart API readback confirms both
  services absent, all 6 LLM and 5 MCP children retain deleted markers, and
  both active child inventories are empty (2026-11-06 11:31 ET).
- [x] Make native service exclusion part of platform initialization. The
  canonical `init.sh` completed; after a server-only restart, the native tool
  confirmed both services and child inventories absent. Repeat is idempotent;
  13 focused tests cover failure handling, credential privacy and child scope
  (2026-11-06 11:33 ET).
- [x] Final Standards, Spec and GoF review found no remaining issue; 13 focused
  tests, 99 file-only checks, compose validation and the post-restart native
  readback pass (2026-11-06 11:33 ET).
- [ ] Publish this follow-up on a fresh ready PR; PR #1453 merged at
  lineage-only scope. Wait for current-head CI and merge.
- [x] Learning → skill: `skills/openmetadata/SKILL.md` now records the
  initialization command, exact service/child exclusion, readback and restart
  procedure (2026-11-06 11:33 ET).

## GoF consult

The existing image's startup and its bundled seed classes were inspected with
their release sources. Startup unconditionally loads the demo lineage, including
soft-deleted endpoints, so deletion alone cannot prevent it returning. The
existing classpath places configuration before release jars. Reuse that seam
for an empty seed resource. A small repository skill tool handles native
service/child cleanup; no OpenMetadata product code or image change is needed.

## Standards

Read-only compose mount, no committed credentials, no image build or database reset.
Compose validation and 98 file-only genericity/path checks pass. The installed
release's actual resource loader reads the override as an empty array.

## Spec

Removed exactly eleven bundled AI demo edges across two sample services.
Startup suppression and post-restart native readback preserve all 85 real
platform edges. The later service cleanup is limited to the two named demo
services and their enumerated sample children.

## GoF

Independent review found no refactor warranted. The fixed native API sequence
uses no new GoF pattern or generalized deletion framework.

## Later operator clarification

The operator named both default AI services as unwanted and requested their
exclusion "part of init". Removing edges alone leaves active service entries.
Initialization must therefore remove both exact services through native soft
deletion, preserve their deleted markers, and verify active absence. The existing
seed loader checks Include.ALL and does not restore these retained markers.
The GoF pattern-selector's default applies to the small standalone skill tool:
one native client and a linear initialization step need no pattern abstraction.
