# 01 — Dual-mode capture contract

**What to build:** Operators and agents share one platform with two capture modes that cannot silently fight Ticket 20: **normal** (silver is system of engagement; bronze only on explicit request or non-edgartools sources) and **strict_release** (always persist immutable evidence artifacts required for relationship bulk-load / release GO). Named flags or env vars document how every later ingest ticket behaves in each mode.

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] Normal vs strict_release modes are named and documented in doctrine-adjacent operator notes (and code constants if wiring is trivial)
- [x] Strict_release always keeps evidence persistence required by release bulk-load; normal does not require bronze for edgartools-sourced SEC objects
- [x] Explicit persist-bronze (or equivalent) is defined for normal mode when an operator asks
- [x] Non-edgartools sources still require immutable archive under both modes
- [x] Acceptance language is clear enough that tickets 03–07 can reference the modes without re-litigating ADR 0002 vs Ticket 20

