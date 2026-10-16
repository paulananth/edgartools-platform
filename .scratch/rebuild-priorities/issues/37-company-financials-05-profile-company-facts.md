# 05 Profile company facts

Priority: 37, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/05-profile-company-facts.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task. Status: claimed. Blocked by: 36. Map: [map](../../company-financials/map.md).

## Question

Run the data-profiling skill on the captured company facts: its parts (company, concept, unit, fact), keys, links to the Company master, time roles (period, filed date, as at), duplicates across filings, and which concepts cover how many companies and years. The findings feed tickets 06 and 07.

Input ready: the long form (`company-facts/cohort-long/`: facts, concepts, entities Parquet), until ticket 09 lets the profiler read the captured files as they are.

## Checklist

- [x] Verify local input availability and check for reusable findings — 2026-10-16 14:03 ET; local inventory: three long-form files, 33,114,407 bytes, no existing findings under the capture root.
- [x] Profile all three related parts together once, retaining complete findings privately under the local proving folder — 2026-10-16 14:06 ET; full scan completed successfully in 49.83 seconds (48.5 seconds profiler time), no sampling, approval remains draft.
- [ ] Report classes, keys, measured links, time roles, repeated filing values and concept coverage; distinguish evidence from proposed interpretation.
- [ ] Resolve unknowns and obtain the operator's explicit findings approval before catalog publication or onboarding.
- [ ] Review the counts-only ticket evidence under Standards, Spec and GoF; run overlap checks before commit and push.
- [ ] Learning → skill: name any durable lesson, or none.

## Execution boundary

Use only `~/.local/share/edgartools/clean-mdm/proving/company-facts/`. Raw values and full findings remain local; the public ticket contains counts and invented examples only. Linking to the existing MDM Company is by CIK lookup; this profiling run alone does not prove live master lookup coverage. Ticket 41's original-JSON reader gap is separate from profiling the existing long form.

## Findings so far

Private evidence: `company-facts/profile-ticket37-20261016/` under the permitted proving root, containing the original findings, report, fingerprints, marked rows, run log and elapsed-time evidence. Do not publish these files: they may contain values from the capture. The findings pin input checksums and the profiler implementation; reuse this run rather than scanning approved inputs again.

| Part | Rows | Measured key | Measured connection |
|---|---:|---|---|
| Companies in capture | 329 | CIK, unique and filled | Every fact CIK resolves to this captured Company list; MDM lookup not tested |
| Concept definitions | 8,495 | Taxonomy plus concept, unique and filled | Every fact taxonomy/concept resolves; 9 taxonomies and 8,418 distinct concept names |
| Reported facts | 5,134,979 | No unique key established by the profiler's search of up to three columns | Two many-to-one links, both inclusion 1.0 |

The facts contain 269 distinct units, 17,252 filing accessions and 44 form labels. The observed period start/end pair is ordered; the generic time inference assigns `filed` to event time and leaves recorded time unknown. This is evidence to interpret in ticket 35, not an approved business time model.

### Interpretation requiring reconciliation

The heuristic calls the Company list reference data and concept definitions master data; it leaves facts unknown because no key was proved. These are unapproved suggestions, not instructions to create a new MDM kind or an RDM Company code set. The operator's scope is existing MDM Companies linked by CIK and financial observations in silver. A domain interpretation, a fact key spanning more than three columns or source position, and repeated filing semantics remain decisions or qualification work.

The suggested `unit > concept` hierarchy is only a measured dependency in this capture, not an approved business hierarchy. Units must remain part of fact identity and comparability. The long-form conversion stores `val` as DOUBLE; production number precision must be proved from the original captured JSON by reader ticket 45, not inferred from this profiling derivative.

The generic findings do not measure complete per-concept Company/year coverage or choose a fact key beyond three columns. Those gaps are recorded explicitly for the mapping/reader qualification in tickets 38 and 45; no second profile or silent classification override has been performed. Findings approval and catalog publication remain pending.

## Progress review

### Standards

Dedicated fresh ticket branch/worktree; evidence contains only counts and schema vocabulary. Raw captures and full profiling findings stay outside the public repository. No provider request, production change or overlap edit.

### Spec

This is a checkpoint, not a completed ticket: the unchecked checklist items remain pending. No operator answer or findings approval has been inferred.

### GoF

The refactor-review skill is available; this checkpoint changes no program code and introduces no design-pattern refactor.
