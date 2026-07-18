# Form 13F usefulness timeline

Type: research
Status: resolved
Blocked by: 01
Blocks: 08

## Question

How does the usefulness of `13F-HR` / `13F-HR/A` filings decay with age for
(a) agent `INSTITUTIONAL_HOLDS` current-at-watermark and short change context,
and (b) human investment analysis of manager/issuer positioning — and what
lookback steps (e.g. latest period only, 3y, 5y, 2013-05-20 floor) are
defensible?

## Exit criteria

- Value-vs-age narrative for institutional holdings.
- Recommended agent window and optional Explore window.
- Note SEC lag / Latest Complete Holdings Period if relevant.

## Answer

**Gist:** Agent usefulness of 13F is step-decaying: current-at-watermark needs
the Latest Complete Holdings Period (lagged, lag in coverage) plus ~12 quarters
of effective holdings for short change context; older XML-era filings mainly
serve Explore archaeology. Restatements supersede and added-holdings
amendments supplement per `(manager, period)` (`effective_thirteenf.py`).
Format floor `2013-05-20` is correctness, not a mandate to load full history
for agents.

**Recommended agent window:** `max(W − 3 years, 2013-05-20)` → `W`.  
**Optional Explore:** full XML-era archive `2013-05-20` → `W` (separate, not
first agent GO freeze).

**Research:** [../research/03-thirteenf-usefulness.md](../research/03-thirteenf-usefulness.md)
