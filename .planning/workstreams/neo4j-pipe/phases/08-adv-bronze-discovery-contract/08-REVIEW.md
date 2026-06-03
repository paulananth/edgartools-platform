---
phase: 08-adv-bronze-discovery-contract
status: clean
reviewed: 2026-06-03
depth: standard
files:
  - edgar_warehouse/application/adv_bronze_discovery.py
  - tests/application/test_adv_bronze_discovery.py
---

# Phase 8 Code Review

## Scope

- `edgar_warehouse/application/adv_bronze_discovery.py`
- `tests/application/test_adv_bronze_discovery.py`

## Findings

No issues found.

## Checks

- Verified the helper does not import the warehouse orchestrator or artifact refresh service.
- Verified discovery uses fixed ADV forms and fixed `sec_company_filing` query text.
- Verified storage reads are routed through `object_storage.read_bytes` or an injected read function.
- Verified tests cover registry discovery, accession filtering, limit behavior, explicit fallback, structured missing/unreadable issues, and no SEC fetch helper calls.

## Residual Risk

Phase 9 still needs to wire this contract into `parse-adv-bronze`, parser execution, idempotency checks, and silver ADV merge behavior.
