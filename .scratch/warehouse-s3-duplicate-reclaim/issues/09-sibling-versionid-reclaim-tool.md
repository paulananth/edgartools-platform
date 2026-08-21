# 09 — Sibling VersionId Reclaim tool

**What to build:** A sibling of the ADR 0004 staging cleanup (not that script) that dry-runs a reviewed TSV, requires a distinct confirm flag to apply, deletes only listed VersionIds in batches of 100, hard-fails if the manifest includes current Canonical Silver, skips Identity Refresh Run directories newer than 24 hours, keeps the union of per-table newest `LastModified` gold `run_id=` prefixes, reports count and GiB per prefix, and treats an empty second run as success. Fixture tests only — no prod delete.

**Blocked by:** None — can start immediately (parallel with 07).

**Status:** resolved

- [x] Default invocation is dry-run and writes a TSV of key, version id, last modified, size, and is-latest
- [x] Apply requires a distinct confirm flag and a reviewed manifest; batches of at most 100 VersionIds
- [x] Manifest containing a current Canonical Silver VersionId is a hard fail
- [x] Fixture tests: noncurrent shards selected, current shards denied; identity run dirs &lt; 24h skipped; gold keep-set is the per-table LastModified union; empty candidate set succeeds
- [x] ADR 0004 staging cleanup is unchanged (`IsLatest=true` under the ephemeral prefix)
