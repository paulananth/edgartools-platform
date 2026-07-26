# Residual holds pipeline status — 2026-07-26

## Execution

| Field | Value |
| --- | --- |
| Name | `residual-holds-20260725T222735Z` |
| Status | **FAILED** at `MdmVerify` (exit 1, 3 retries) |
| ARN | `arn:aws:states:us-east-1:690839588395:execution:edgartools-prod-residual-holds-graph:residual-holds-20260725T222735Z` |

### Stages completed

| Stage | Result |
| --- | --- |
| MdmSecurities | OK (after pull retry; mdm-large 8 GiB) |
| MdmPersons | OK |
| MdmIsInsider | OK |
| MdmHolds | OK |
| MdmCompanyHolds | OK |
| MdmInstitutionalHolds | OK (0 INSTITUTIONAL_HOLDS rows derived — still empty in MDM) |
| MdmExport | OK |
| MdmSync | OK (but **partial** type filter — see root cause) |
| MdmVerify | **FAIL** |

## Counts (prod, 2026-07-26)

### MDM Postgres (after residual)

| Type | Count |
| --- | ---: |
| MANAGES_FUND | 138,585 |
| EMPLOYED_BY | 19,147 |
| HOLDS | **5,253** |
| COMPANY_HOLDS | **1,778** |
| IS_INSIDER | **1,304** |
| INSTITUTIONAL_HOLDS | **0** |
| **Total edges** | **166,067** |
| mdm_security | **97** |

### Active graph (Ticket 20 — still live)

| Field | Value |
| --- | --- |
| Generation | `ticket20-strict-endpoint-seal-850ea34-20260725T130457Z` |
| Status | **activated** |
| Nodes / edges | 193,063 / 157,732 |
| Edges | EMPLOYED_BY 19,147 + MANAGES_FUND 138,585 |
| Residual types on active | **empty** (IS_INSIDER / HOLDS / COMPANY_HOLDS / security nodes) |

### Candidate generation (from partial sync)

| Field | Value |
| --- | --- |
| Generation | `69e139b0-f4d4-46bf-b4f2-0f69571e2277` |
| Status | **building** (never verified) |
| Nodes / edges | 39,120 / 8,335 |
| Nodes | Company 32,970 · Person 6,053 · Security **97** |
| Edges | HOLDS 5,253 · COMPANY_HOLDS 1,778 · IS_INSIDER 1,304 |
| Missing | Fund, Adviser, AuditFirm, EMPLOYED_BY, MANAGES_FUND, INSTITUTIONAL_HOLDS |

## Root cause (5-whys)

1. **Symptom:** `verify-graph` failed; SF execution FAILED after MDM residual filled.
2. **Why:** Parity showed `mdm_minus_graph` for IS_INSIDER (1304), HOLDS, COMPANY_HOLDS vs active graph.
3. **Why active missing residual edges?** Residual `MdmSync` only materialised a **type-filtered** candidate gen; **active pointer unchanged**.
4. **Why verify failed against active?** `verify-graph` without `--generation-id` checks the **active** generation (by design).
5. **Root cause:** Residual SM combined (a) **partial sync** (incomplete candidate) with (b) **active-scoped verify** — so residual MDM can never pass verify until a **full** candidate is built and verified (then operator activates).

## Fix (code)

`residual_holds_graph` SM:

- `MdmSync`: full `sync-graph --generation-id $$.Execution.Name --limit-per-type 200000` (no type filters).
- `MdmVerify`: `verify-graph --skip-native-app --generation-id $$.Execution.Name`.

## Activation

**Do not activate** `69e139b0…` (incomplete). After full-candidate PASS, operator may:

```bash
mdm graph-activate --generation-id <Execution.Name>
```

## INSTITUTIONAL_HOLDS

Still **0** in MDM after derive step “OK” — separate investigation (silver 13F
path / eligibility / derive filters), not the verify failure root cause.
