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

## Full candidate repair (2026-07-26)

After SM fix deploy (#270), one-off full materialization (MDM residual already present):

| Step | Result |
| --- | --- |
| `sync-graph --generation-id residual-full-20260726T010010Z --limit-per-type 200000` | **OK** — nodes **193,323** · edges **166,067** |
| `verify-graph --skip-native-app --generation-id residual-full-20260726T010010Z` | **PASS** (exit 0) · status **verified** |

| Field | Value |
| --- | --- |
| Candidate generation | `residual-full-20260726T010010Z` |
| Candidate status | **verified** |
| Active generation (unchanged) | `ticket20-strict-endpoint-seal-850ea34-20260725T130457Z` |
| Parity | MDM 166,067 edges = graph 166,067 (includes HOLDS / COMPANY_HOLDS / IS_INSIDER) |

### Residual edge counts now on verified candidate

| Type | Count |
| --- | ---: |
| MANAGES_FUND | 138,585 |
| EMPLOYED_BY | 19,147 |
| HOLDS | 5,253 |
| COMPANY_HOLDS | 1,778 |
| IS_INSIDER | 1,304 |
| INSTITUTIONAL_HOLDS | **0** |

## Activation

**Not activated** (operator decision). Incomplete gen `69e139b0…` must **not** be activated.

To activate the verified full candidate:

```bash
# via ECS / CLI with prod MDM image + snowflake secret
mdm graph-activate --generation-id residual-full-20260726T010010Z
```

## INSTITUTIONAL_HOLDS

Still **0** in MDM after derive step "OK" as of this doc's original writing —
not the verify failure root cause.

**Update 2026-07-26 (later same day):** root-caused via live prod evidence,
not silver 13F fetch/eligibility. `SEC_THIRTEENF_HOLDING` already has 6.8M
rows in Snowflake SOURCE. CloudWatch confirms the derive step's actual skip
reason: `{"event": "mdm_relationship_skip", "rel_type":
"INSTITUTIONAL_HOLDS", "reason": "missing_source_table", "source_table":
"sec_thirteenf_filing"}`
(`mdm-mdm-large/edgar-warehouse/7fd06878e8254bcab9cbdb4263066ab8`,
2026-07-25T23:26:52Z). `ShardedSilverReader._TABLES`
(`edgar_warehouse/silver_support/sharded_reader.py`) never registered
`sec_thirteenf_filing` as a cross-shard view (added same commit as
`sec_thirteenf_holding`, d20cad8, but omitted from the allowlist), so the
derive JOIN raises a DuckDB catalog error that the graceful missing-table
skip mistakes for an empty universe. Fixed by adding the table name (plus
sibling `sec_employment_event`, EDGE-09's gap) to `_TABLES`. No SEC refetch
needed — see `.scratch/release-readiness/issues/06-define-full-chain-launch-gate.md`
for the full chain of evidence.
