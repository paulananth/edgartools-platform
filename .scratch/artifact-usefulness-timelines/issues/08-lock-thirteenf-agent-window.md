# Lock 13F agent lookback window

Type: grilling
Status: resolved
Blocked by: 01, 03, 07
Blocks: 12
Assignee: grok-session

## Question

What is the locked **agent** lookback for `13F-HR` / `13F-HR/A` relative to
watermark `W` (and XML floor), and is full 2013→W Explore archive in-scope for
the same GO freeze?

## Exit criteria

- Locked agent window string (e.g. `max(W-3y, 2013-05-20)`).
- Yes/no: full XML-era 13F in first agent GO freeze.

## Answer

**Agent window (locked):**

```text
filing_date ∈ [max(W − 3 years, 2013-05-20), W]
```

- **3 years** of 13F for agent `INSTITUTIONAL_HOLDS` current set + short change
  context (prior product grill + research ticket 03).
- **2013-05-20** remains the **XML format floor only** — never claim or load
  pre-XML text 13F; if `W − 3y` is before that floor, start at the floor.

**Full XML-era archive (2013-05-20 → W) in the same first agent GO freeze:**
**No.** Under agent-first destination (ticket 02), full history is optional
**Explore backfill**, not required for first agent-useful PASS.

**Amendment rule (unchanged):** for each (manager, period_of_report) in-window,
apply restatement supersede + added-holdings supplement
(`effective_thirteenf.py`); Latest Complete Holdings Period lag stays in
coverage metadata.

## Evidence / prior confirmations

- Product grill (earlier session): 13F depth = 3 years before watermark.
- Research: [research/03-thirteenf-usefulness.md](../research/03-thirteenf-usefulness.md).
- Destination: agent-first + step lookbacks (ticket 02).
- Interactive re-prompt for this ticket was declined; resolution uses the above
  already-confirmed answers (not a new override).
