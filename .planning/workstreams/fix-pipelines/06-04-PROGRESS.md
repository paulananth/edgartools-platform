
## 2026-07-12 — Deploy + OOM-fix verification (session resume)

- Clock skew blocker RESOLVED (local UTC == AWS UTC, 2s drift).
- Deployed medium task-def memory bump via deploy-aws-application.sh (AWS_PROFILE=edgartools-690, --skip-build, images pinned to current :dev digests → image unchanged, memory 2048→4096 only).
  - warehouse @sha256:ec2f68a7...  mdm @sha256:12c2c45e...
  - edgartools-dev-medium:39 (2048 MB) → :40 (4096 MB) VERIFIED.
  - load_history state machine now references edgartools-dev-medium:40.
- OOM-fix test run launched: load-history-oomtest-1783868231, input {"total_cik_limit": 20}
  - Goal: prove per-window bootstrap-next gold build (sec_financial_fact, 2.7M rows) survives at 4 GB (exec #3 OOM'd exit 137 at 2 GB).
