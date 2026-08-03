Type: research
Status: claimed

## Question

What is the real, safe headroom for increasing parallelism against SEC
EDGAR before hitting rate-limit throttling or blocking -- as a hard input
constraint on tickets 03 and 04?

Specifically:
- SEC's documented per-IP rate limit (currently assumed ~10 req/sec in
  CLAUDE.md's "Key invariants" section) -- confirm current published
  guidance and any burst/short-window allowance.
- Current in-process limiter: `sec_client.py`'s `pyrate_limiter` bucket,
  9 req/sec per ECS task.
- Whether ECS tasks running concurrently (e.g. `BOOTSTRAP_BATCH_CONCURRENCY`
  2-5 today) share a single outbound IP (NAT gateway) or get distinct
  IPs -- this determines whether task-count parallelism and intra-task
  concurrency compete for the same 10 req/sec ceiling or not. Check the
  actual VPC/NAT Terraform config (`infra/terraform/accounts/prod/`)
  rather than assuming.
- Whether SEC's guidance distinguishes bulk/bot traffic patterns that
  would make aggressive parallelism (even under the numeric limit) a
  ToS/blocking risk regardless of raw req/sec math.

## Done when

A short, cited answer (SEC's own published fair-access guidance, plus the
actual NAT/VPC topology from Terraform) that ticket 03 and ticket 04 can
both treat as a hard ceiling when comparing concurrency options.
