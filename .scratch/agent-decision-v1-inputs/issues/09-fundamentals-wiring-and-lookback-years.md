# Confirm fundamentals wiring and lookback years

Type: research
Status: resolved
Blocked by: none

## Question

Is `bootstrap-fundamentals` (entity-facts / per-filing / thirteenf)
integrated into live `daily_incremental` and `load_history`? What year
lookback actually applies (operator recalled 5 years)?

Determine specifically:

1. In-repo Step Functions builders (`deploy-aws-application.sh`): which
   states invoke `bootstrap-fundamentals`, with which `--mode`, on
   `load_history` vs `daily_incremental` (and any other warehouse SM).
2. Live prod state-machine definitions (`edgartools-prod-load-history`,
   `edgartools-prod-daily-incremental`): same modes present or absent.
3. Lookback: `--fundamentals-lookback-years` /
   `WAREHOUSE_FUNDAMENTALS_LOOKBACK_YEARS` and per-family overrides
   (`filing`, `item-202`, `proxy`, `thirteenf`, entity-facts if any).
   Code default vs SM-injected value vs live env. Confirm or refute a
   5-year limit. Entity-facts/companyfacts may be unbounded even when
   artifact families are windowed.
4. Do not re-decide Ticket 08 (whether v1 waits on a backfill).

Read-only. Do not implement.

Save findings at
`.scratch/agent-decision-v1-inputs/research/09-fundamentals-wiring-and-lookback.md`.

## Answer

**load_history: yes** (live Stage 1B `FetchEntityFacts` / per-filing /
thirteenf). **daily_incremental: no** (only `company-identity`; wiring is
still-open fundamentals-daily ticket 04). **Year limit is 2 years** for
artifact fetch/parse and load_history filing discovery, **not 5**.
entity-facts/companyfacts has **no** year filter (live FY 2009–2026). Five
years is the old proxy *agent usefulness* window (later narrowed) and CAGR
math, not the fetch gate.
[research](../research/09-fundamentals-wiring-and-lookback.md)
