# GO claim language for partial history

Type: grilling
Status: resolved
Blocked by: 12
Blocks: none
Assignee: grok-session

## Question

What exact GO / PASS wording do we allow when windows are partial (8-K 2y,
13F 3y, proxy 5y in-band) so Ticket 20 and agent-grade evidence do not
overclaim “complete since 2013”?

## Exit criteria

- Approved claim phrases per relationship type.
- Forbidden overclaims listed.

## Answer

**Locked 2026-07-18 (wayfinder grill Q1–Q4).**

### PASS scope

Ticket 20 **PASS / GO** means: **agent-window bulk-load complete only** —
every frozen candidate inside declared `coverage_by_document_type` windows has
a terminal ledger outcome. It does **not** mean full SEC history, Form 3/4/5
completeness, or financial feature (CAGR) completeness.

### Binding tuple (required on every PASS)

Every PASS evidence statement / header must cite:

1. inventory **fingerprint** `F`
2. Release Data **watermark** `W`
3. **`coverage_by_document_type`** (13F, proxy, Item 5.02 8-K windows)

### Approved claim phrases

```text
Ticket 20 PASS:
  Required relationship sources for EMPLOYED_BY and INSTITUTIONAL_HOLDS are
  bulk-load complete for agent windows at watermark W (fingerprint F):
    13F [max(W−3y, 2013-05-20), W];
    proxy [W−5y, W] (latest-in-band baseline only);
    Item 5.02 / ambiguous 8-K [W−2y, W].

Per-type (approved):
  13F agent inventory complete for [start, W].
  Proxy agent inventory complete for [W−5y, W] (no pre-band baseline).
  Item 5.02 8-K agent inventory complete for [W−2y, W].
```

Fill concrete ISO dates for `start` / `W` when writing evidence.

### Forbidden overclaims

Never on PASS/GO, Agent View, or evidence headers:

| Forbidden |
| --- |
| “Complete since 2013” / “full history” for all relationship forms |
| “All 8-Ks loaded” |
| “All proxies since IPO / 2013” |
| “13F complete for full XML era” when freeze is only the agent 3y window |
| “EMPLOYED_BY enumerates every employee” |
| “Form 3/4/5 complete” as Ticket 20 PASS |
| “CAGR / financials complete” as Ticket 20 |
| Treating top-level `coverage_start` as agent coverage for every form |
| Explore archive complete = agent GO |

## Grill log

| # | Topic | Decision |
| --- | --- | --- |
| 1 | PASS scope | **Agent-window bulk-load complete only** — not full SEC history; not Form 3/4/5 or CAGR |
| 2 | PASS binding tuple | **fingerprint + watermark W + `coverage_by_document_type`** |
| 3 | Approved PASS phrases | Full phrase pack (Ticket 20 summary + per-type lines) |
| 4 | Forbidden overclaims | Accept ban list above |
