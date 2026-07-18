# Lock proxy agent lookback window

Type: grilling
Status: resolved
Blocked by: 01, 05, 07
Blocks: 12
Assignee: grok-session

## Question

What is the locked proxy policy: baseline-always + history band (proposal:
**latest ≤ W always + W − 5 years**)?

## Exit criteria

- Locked baseline rule + history band.
- Confirm baseline may predate history band.

## Answer

**Agent proxy window (locked):**

```text
DEF 14A / DEF 14A/A / DEFA14A / PRE 14A:
  filing_date ∈ [W − 5 years, W]
```

Within that band:

- Include **all** such proxies for in-scope companies (history + any “current”
  proxy that falls in band).
- **Current-at-watermark baseline** = latest definitive proxy with
  `filing_date ≤ W` **and** `filing_date ≥ W − 5 years` (if any).

**Baseline may predate W−5y?** **No.** Never load proxies older than
`W − 5 years` for first agent GO. If no proxy exists in band, employment
baseline is **missing** until a newer proxy appears (fail-closed / coverage
gap for that issuer — not filled by ancient DEF 14A).

**Explore:** proxies older than W−5y remain optional later archive, not agent
GO denominator.

## Grill log

| # | Decision |
| --- | --- |
| 1 | History band **W − 5 years → W** (with latest-in-band as baseline) |
| 2 | **No** load of proxies older than W−5y (rejects “baseline always if ancient”) |
