# Lock Form 3/4/5 agent lookback window

Type: grilling
Status: resolved
Blocked by: 01, 06
Blocks: 12
Assignee: grok-session

## Question

What activity lookback and “current holds” rule lock for Forms 3/4/5 on the
agent surface (proposal: **W − 2 years** activity + derived current holds)?

## Exit criteria

- Locked activity window and current-holds rule.
- Note ownership path vs Ticket 20 freeze.

## Answer

**Agent Form 3/4/5 window (locked 2026-07-18, product choice a):**

```text
Forms: 3, 4, 5 (+ amendments as applicable)
Activity: filing/transaction date ∈ [W − 2 years, W]
Plus: current derived holds (snapshot at W — always in agent surface)
```

| Signal | Rule |
| --- | --- |
| **Recent activity** (Insider Watch tape) | **`W − 2 years`** only for first agent GO |
| **Current derived holds** | Always published as current-at-watermark snapshot (not “every Form 4 ever”) |
| **Deeper Form 4 archaeology** | Explore-only; not agent GO denominator |

**Not Ticket 20 freeze path.** Ownership is silver-once / Branch A (`parse-ownership-bronze` → ownership silver → MDM `IS_INSIDER` / `HOLDS`). Completing Ticket 20 (proxy / Item 5.02 / 13F) does **not** prove Form 3/4/5 activity is complete for the agent window; expanding Form 3/4/5 depth does **not** expand the Ticket 20 freeze.

**Rejected alternatives:** **b** W−1y activity (tighter; not chosen); full history since first Form 3 (Explore only).

## Grill log

| # | Decision |
| --- | --- |
| 1 | Activity lookback **`W − 2 years → W`** |
| 2 | **Current derived holds** always in agent surface |
| 3 | Ownership path **orthogonal** to Ticket 20 relationship freeze |
| 4 | Pre-2y Form 4 tape = Explore, not agent GO |
