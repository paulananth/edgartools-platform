# 05 — Catalog novelty-only refresh (submissions / daily index)

**What to build:** Submissions and daily-index discovery treat silver catalogs/checkpoints as system of engagement: network only to discover **new** accessions or business dates when prior work is complete; force remains available for full refresh.

**Blocked by:** 01 — Dual-mode capture contract; 02 — Skip and network metrics.

**Status:** resolved

- [x] Finalized daily index dates do not re-download on no-op catch-up re-runs
- [x] Submissions refresh for a fully synced CIK prefers novelty detection over full history re-pull unless force
- [x] New filings/dates still get discovered on subsequent runs
- [x] Metrics show catalog skips vs network where applicable

