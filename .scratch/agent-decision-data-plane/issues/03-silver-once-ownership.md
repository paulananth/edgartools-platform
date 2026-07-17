# 03 — Silver-once skip for ownership (accession + parser_version)

**What to build:** Ownership (Forms 3/4/5) capture/parse skips SEC/edgartools network when silver already has a successful parse for that accession at the current parser_version; force re-fetches and overwrites silver. Dual-mode from ticket 01: strict_release still archives evidence as required; normal does not require bronze.

**Blocked by:** 01 — Dual-mode capture contract; 02 — Skip and network metrics.

**Status:** ready-for-agent

- [ ] Second run over already-parsed ownership accessions at same parser_version performs no network fetch for those accessions
- [ ] Force (or equivalent) re-invokes network and updates silver
- [ ] Parser_version bump allows re-fetch without manual force of the entire universe (or documents the supported upgrade path)
- [ ] Metrics from ticket 02 reflect ownership skips vs fetches
- [ ] Strict_release mode still satisfies Ticket 20 evidence persistence expectations for ownership artifacts when that mode is on
