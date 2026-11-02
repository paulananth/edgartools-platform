# 169: Company financials run through Bookkeeping and the Change Journal

Priority: 169. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 08:23 ET (operator, 2026-11-02: "Is company financial go through bookkeeping and change journal", then "What do we need to do to introduce bookkeeping and change journal in accordance with elimination of 7 wastes", then "Yes").

Type: task. Status: open. Blocked by: none.

## Question

The company financials (facts, line items, measures) are built by hand: `rules/source-sequence.yaml` gives `sec.company-facts` `target: null` ("its silver landing target comes with ticket 46", never filled), the Bookkeeping feed test refuses its feed, and nothing records the facts files in the Change Journal. What does it take to run them as tracked work that skips unchanged files, without waste?

## The seven wastes, applied

| Waste | Here |
|---|---|
| Over-production | Only the three tables the product uses; no gold, no new target kind |
| Motion | The step order lives in the rules, not in a person's memory |
| Over-processing | The Journal skips an unchanged file; rules changes reprocess; ticket 48's proof is carried forward, not repeated |
| Waiting | The deadline is sized from one measured real run |
| Defects | The landing step writes the quality results file (ticket 165); bounds are checked first |
| Transport, Inventory | Existing `land` and silver commands; no copied captures; test stores and containers removed |

## Parts

- [ ] GoF consult before any code
- [ ] `sec.company-facts` gets one Bookkeeping target (`silver`) with three steps in order: land `company_fact`, line items, measures; each step reads the previous step's verified output (`run:` binding). The source sequence, the feed resolver and the load doc ("financial facts remain in their captured evidence") say so
- [ ] The Change Journal records the captured facts files; the processing identity is the digest of the facts, line-item and measure rules; no source-specific code in the Journal (its independence stays)
- [ ] Find out whether line items and measures can rebuild only the Companies whose facts changed; if not, the first version rebuilds all and the ticket says why
- [ ] A limited proof only: one Company's facts file, both orders, a second pass that changes nothing, an unchanged file skipped, a changed rule reprocessed. No full cohort rerun
- [ ] One real run is timed and its deadline sized from the measure (say the time before starting it)
- [ ] The landing step writes `QUALITY_RESULTS_FILE`; the three silver tables get their first quality checks (operator decides the checks)
- [ ] Stores and containers a test run leaves are removed
- [ ] Learning → skill: `bookkeeping`, `change-journal` and `company-financials` skills name the target, the steps and the identity
