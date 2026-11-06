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
- [ ] Publish a ready PR and verify its final head.
- [x] Learning → skill: openmetadata's Exclude bundled demo lineage records
  the unconditional seeding cause, override and required restart readback
  (2026-11-06 07:20 ET).

## GoF consult

The existing image's startup and its bundled seed classes were inspected with
their release sources. Startup unconditionally loads the demo lineage, including
soft-deleted endpoints, so deletion alone cannot prevent it returning. The
existing classpath places configuration before release jars. Reuse that seam
for an empty seed resource; no program, image or design-pattern change is needed.

## Standards

Read-only compose mount, no credentials, no image build or database reset.
Compose validation and 98 file-only genericity/path checks pass. The installed
release's actual resource loader reads the override as an empty array.

## Spec

Removed exactly eleven bundled AI demo edges across two sample services.
No assets deleted. Startup suppression and post-restart native readback satisfy
the request to keep those examples out; the real graph is preserved.

## GoF

Independent review found no refactor warranted: the stable compose seam is
sufficient. No new code abstractions or algorithms were introduced.
