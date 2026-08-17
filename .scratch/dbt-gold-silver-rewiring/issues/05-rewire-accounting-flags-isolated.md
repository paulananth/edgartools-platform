# 05 — Rewire accounting_flags onto Silver, Isolated from the Forensic-Score Fix

**What to build:** `accounting_flags` reads from dbt silver via `ref()`
instead of its current Python builder. Kept as its own ticket, separate from
Tickets 02-04, because this table has a known upstream fragility: a live
forensic-score (Beneish M / Altman Z / Piotroski F) masking bug tracked and
fixed separately (see CLAUDE.md / the platform's own accounting-flags
incident history). This ticket rewires the read path only — it does not
touch forensic-score computation logic, and should run its reconciliation
check against the *already-fixed* output, not the pre-fix output.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] `accounting_flags` sources exclusively via `ref()` from dbt silver's
      `sec_accounting_flag` model
- [ ] The cutover validation standard passes, explicitly re-verified against
      the current (post-fix) forensic-score output — not a stale pre-fix
      baseline
- [ ] `dbt run --full-refresh` succeeds against prod
