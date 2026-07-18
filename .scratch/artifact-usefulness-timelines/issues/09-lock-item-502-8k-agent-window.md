# Lock Item 5.02 8-K agent lookback window

Type: grilling
Status: resolved
Blocked by: 01, 04, 07
Blocks: 12
Assignee: grok-session

## Question

What is the locked agent lookback for Item 5.02 / ambiguous 8-Ks (default
proposal: **W − 1 year**), and are older 5.02 events Explore-only?

## Exit criteria

- Locked window for artifact-required 8-K candidates.
- Confirm unrelated 8-K exclusion.

## Answer

**Agent window (locked):**

```text
8-K / 8-K/A with Item 5.02 OR missing/ambiguous items:
  filing_date ∈ [W − 2 years, W]
```

**Older than W−2y Item 5.02 events:** **Explore-only** (not first agent GO freeze).

**Unrelated 8-K** (items prove no 5.02): **never bulk-download** for this gate;
metadata-backed `not_applicable` only.

**Note:** Product chose **2 years** (not the earlier 1-year default). Proxy
baseline + 5y history still supplies longer employment structure; 8-K band is
recent-event delta only.

## Grill log

| # | Decision |
| --- | --- |
| 1 | Agent 8-K 5.02/ambiguous: **W − 2 years → W** |
| 2 | Older 5.02 = Explore-only; no-5.02 items = no bulk download |
