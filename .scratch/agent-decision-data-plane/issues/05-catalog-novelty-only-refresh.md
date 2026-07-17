# 05 — Catalog novelty-only refresh (submissions / daily index)

**What to build:** Submissions and daily-index discovery treat silver catalogs/checkpoints as system of engagement: network only to discover **new** accessions or business dates when prior work is complete; force remains available for full refresh.

**Blocked by:** 01 — Dual-mode capture contract; 02 — Skip and network metrics.

**Status:** ready-for-agent

- [ ] Finalized daily index dates do not re-download on no-op catch-up re-runs
- [ ] Submissions refresh for a fully synced CIK prefers novelty detection over full history re-pull unless force
- [ ] New filings/dates still get discovered on subsequent runs
- [ ] Metrics show catalog skips vs network where applicable
