# Phase 4: SEC Rate Limiting - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-16
**Phase:** 04-SEC Rate Limiting
**Areas discussed:** What "concurrent" means, sec_client.py throttling, enforcement location, minimum floor

---

## What "concurrent" means

| Option | Description | Selected |
|--------|-------------|----------|
| ECS task concurrency (Map MaxConcurrency) | Cap number of parallel ECS tasks — max 5 tasks simultaneously, each making sequential SEC calls | ✓ |
| HTTP connection concurrency within a task | Allow 2–5 parallel HTTP requests per task (requires asyncio/threading refactor) | |
| Both | Cap tasks at 5 AND add per-task parallelism | |

**User's choice:** ECS task concurrency (Map MaxConcurrency)
**Notes:** Within each ECS task, SEC calls remain sequential (single-threaded). The Map state MaxConcurrency is the meaningful lever.

---

## sec_client.py throttling

| Option | Description | Selected |
|--------|-------------|----------|
| No — task concurrency cap is enough | With max 5 parallel tasks each making sequential calls, no per-request delay needed | |
| Yes — add small delay (e.g. 0.1s) between calls | Simple configurable sleep between requests | |
| Yes — add pyrate-limiter to sec_client.py | Use same pyrate-limiter package edgartools uses; proper rate limiter matching library behavior | ✓ |

**User's choice:** Add pyrate-limiter at 9 req/sec
**Notes:** Match EDGAR_RATE_LIMIT_PER_SEC (edgartools default). Package already in uv.lock. No new env var.

---

## Where enforcement lives

| Option | Description | Selected |
|--------|-------------|----------|
| Hardcode MaxConcurrency=5 | Remove BOOTSTRAP_BATCH_CONCURRENCY variable entirely | |
| Keep variable, add deploy-time validation | Fail deploy if value outside [2, 5] | |
| Keep variable, update default to 5 | Change default from 10 → 5; trust operators | ✓ |

**User's choice:** Keep variable, just update the default to 5
**Notes:** No hard validation gate. BOOTSTRAP_BATCH_CONCURRENCY remains configurable for testing/ops.

---

## What the minimum of 2 means

| Option | Description | Selected |
|--------|-------------|----------|
| Documentation only | Note recommended floor in CLAUDE.md/runbook; no code enforcement | ✓ |
| Soft warning at deploy time | Print warning if < 2 but still deploy | |
| Implied by default of 5 — no explicit floor needed | Setting default to 5 naturally satisfies the minimum | |

**User's choice:** Documentation only
**Notes:** Document in CLAUDE.md platform ops section that below 2 concurrent tasks is not recommended for production loads.

---

## Claude's Discretion

- Rate limiter implementation pattern: use `pyrate_limiter.Rate(9, Duration.SECOND)` + `InMemoryBucket` + `Limiter` as a module-level singleton in `sec_client.py`, same pattern as edgartools.
- Whether to update inline comments in `deploy-aws-application.sh` to explain the 2–5 range.

## Deferred Ideas

- Per-task HTTP parallelism (async/threading within an ECS task) — future phase
- Hard deploy-time validation of BOOTSTRAP_BATCH_CONCURRENCY range — user chose documentation-only
- Shared cross-task rate limiter (DynamoDB token bucket) — over-engineering for current scale
