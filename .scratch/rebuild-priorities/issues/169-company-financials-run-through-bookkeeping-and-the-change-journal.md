# 169: Company financials run through Bookkeeping and the Change Journal

Priority: 169. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 08:23 ET (operator, 2026-11-02: "Is company financial go through bookkeeping and change journal", then "What do we need to do to introduce bookkeeping and change journal in accordance with elimination of 7 wastes", then "Yes").

Type: task. Status: in progress (Claude, 2026-11-02 09:12 ET; operator: "Agreed" to start). Blocked by: none.

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

- [x] GoF consult before any code (2026-11-02 09:12 ET): leave the target manifest and the worker registry; both are built for a new step ("a new profile is a new module and an entry in `PROFILES`; Bookkeeping does not change"); add, do not refactor
- [ ] `sec.company-facts` gets one Bookkeeping target (`silver`) with three steps in order: land `company_fact`, line items, measures; each step reads the previous step's verified output (`run:` binding). The source sequence, the feed resolver and the load doc ("financial facts remain in their captured evidence") say so
- [ ] The Change Journal records the captured facts files; the processing identity is the digest of the facts, line-item and measure rules; no source-specific code in the Journal (its independence stays)
- [ ] Find out whether line items and measures can rebuild only the Companies whose facts changed; if not, the first version rebuilds all and the ticket says why
- [ ] A limited proof only: one Company's facts file, both orders, a second pass that changes nothing, an unchanged file skipped, a changed rule reprocessed. No full cohort rerun
- [ ] One real run is timed and its deadline sized from the measure (say the time before starting it)
- [ ] The landing step writes `QUALITY_RESULTS_FILE`; the three silver tables get their first quality checks (operator decides the checks)
- [ ] Stores and containers a test run leaves are removed
- [ ] Learning → skill: `bookkeeping`, `change-journal` and `company-financials` skills name the target, the steps and the identity

## What I found (2026-11-02 09:12 ET)

Read-only, from the code. Bookkeeping and the Journal are already source-neutral; only the silver step is missing.

- A source declares its work as \`bookkeeping.targets\` in its \`source.yaml\`, as ordered steps (\`operation\`, \`requires\`, \`key\`, \`leases\`, \`checks\`). \`sec.company\` shows the shape: \`source.read\` steps, \`source.combine\`, \`mdm.prepare\`, \`mdm.merge\`, then \`journal.record\`.
- The operations that exist: \`artifact.copy\`, \`journal.record\`, \`mdm.merge\`, \`mdm.prepare\`, \`mdm.publish\`, \`provider.capture\`, \`source.combine\`, \`source.read\`. **There is no silver operation.** The "Bookkeeping silver-landing step" named in the map was never built.
- \`journal.record\` and \`changed_files\` are generic: the processing identity is the digest of the source's rules plus its shared inputs; the Journal skips a file recorded under the same identity and key and content hash. Nothing in them names a source, so company facts can use them unchanged as the last step.
- \`mdm/clean/target_manifest.py\` forms each step's units from the declaration by operation (\`FORMS\`), and "names nothing about a source or a kind".
- A worker is one module in \`edgar_warehouse/workers/\` plus an entry in \`PROFILES\`.
- Local silver: no silver connection is configured on this machine (the connection files only unset it), so an end-to-end test uses a Postgres test container (OrbStack works), like \`tests/integration/test_company_fact_silver.py\`.

## Slices (each ends with a limited proof, no cohort rerun)

1. **Land the facts.** New worker \`silver.land\` (reads a verified \`source.read\` output, calls \`silver_writer.land\`, writes the quality results file), its \`FORMS\` entry, a \`silver\` target on \`sec.company-facts\` with steps \`facts\` (source.read), \`land\` (silver.land), \`processed\` (journal.record). Proof: one Company's file, a second pass changes nothing, an unchanged file is skipped, a changed rule reprocesses.
2. **Derive line items and measures.** New worker \`silver.derive\` (calls \`line_items.build\` and \`measures.build\`), two more steps after \`land\`. First check whether they can rebuild only the Companies whose facts changed.
3. **Time one real run, then size the deadline**; add the first quality checks (operator decides them); update the sequence file, the load doc and the three skills.
