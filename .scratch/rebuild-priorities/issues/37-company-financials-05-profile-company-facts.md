# 05 Profile company facts

Priority: 37, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/05-profile-company-facts.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task. Status: claimed. Blocked by: 36. Map: [map](../../company-financials/map.md).

## Question

Run the data-profiling skill on the captured company facts: its parts (company, concept, unit, fact), keys, links to the Company master, time roles (period, filed date, as at), duplicates across filings, and which concepts cover how many companies and years. The findings feed tickets 06 and 07.

Input ready: the long form (`company-facts/cohort-long/`: facts, concepts, entities Parquet), until ticket 09 lets the profiler read the captured files as they are.

## Checklist

- [x] Verify local input availability and check for reusable findings — 2026-10-16 14:03 ET; local inventory: three long-form files, 33,114,407 bytes, no existing findings under the capture root.
- [x] Profile all three related parts together once, retaining complete findings privately under the local proving folder — 2026-10-16 14:06 ET; full scan completed successfully in 49.83 seconds (48.5 seconds profiler time), no sampling, approval remains draft.
- [x] Report classes, keys, measured links, time roles, repeated filing values and concept coverage; distinguish evidence from proposed interpretation — 2026-10-16 14:24 ET; original full findings plus a 5.48-second targeted qualification on their pinned derivative. Per-concept counts reconcile to all 5,134,979 rows; key and coverage results below. Actual MDM lookup remains untested, not silently inferred from internal links.
- [x] Authenticate original capture receipts and check integer representability independently of analytical policy — 2026-10-16 14:30 ET; all 368 captured files match raw checksums and byte counts, raw counts reconcile to the derivative, and one changed integer is traced privately to its source observation. Full receipt/count check took 22.31 seconds; no provider requests.
- [x] Inventory every original source element before asking analytical-policy questions — 2026-10-16 14:46 ET; all 368 original documents and 5,134,979 observations visited without sampling in 94.03 seconds; 23 structural paths / 16 scalar elements, nine observation fields, and 38 additional metadata-only Company headers. Public [element inventory](../evidence/company-financials-37-source-elements.md); complete 8,495-concept catalog and detailed evidence remain private.
- [x] Record operator clarification on skill responsibility and integer widths — 2026-10-16 14:46 ET; data-profiling proposes classification/routing, operator approves, data-onboarding implements. Integer fields/counters use BIGINT / 64-bit long. No time-model answer or findings approval inferred.
- [ ] Resolve unknowns and obtain the operator's explicit findings approval before catalog publication or onboarding.
- [x] Review the counts-only ticket evidence under Standards, Spec and GoF; run overlap checks before commit and push — 2026-10-16 14:16 ET; progress review below, counts reconciled to private findings, whitespace and both guard passes clean, checkpoint 8377111a pushed. The incomplete reporting/approval items stay open.
- [x] Learning → skill: none — 2026-10-16 14:16 ET; existing profile-once, unknowns and approval rules apply. Original-JSON reading changes are isolated in ticket 41 / PR #1016, not silently applied to these draft findings.

## Execution boundary

Operator steering, 2026-10-16: complete discovery of all original source elements first. The time-model choice is not a prerequisite for source discovery. The previous Parquet-only profile did not by itself prove a complete original-source inventory; the original-source inventory linked above closes that gap while preserving the existing draft findings.

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

The generic findings did not measure complete per-concept Company/year coverage or test a fact key beyond three columns. A targeted qualification below closes those measurement gaps without repeating the profiler or changing its draft findings. Choosing the production grain, interpreting classes, proving original numeric precision and approving the findings remain open. Findings approval and catalog publication remain pending.

### Targeted qualification of the pinned derivative

Completed 2026-10-16 14:24 ET. A local, read-only DuckDB qualification took 5.48 seconds. The fact file's checksum matched the original findings before the query and again when sealing the evidence. The original profiler findings remain unchanged. Private artifacts beside them:

- `concept-coverage.json`: every taxonomy/concept's row count, Company count, unit count, observed period-end years, Company/end-year combinations, distinct period ends and instant/duration counts.
- `qualification-summary.json`: counts below and explicit limits.
- `qualify-profile37.py`: exact executed qualification code.
- `qualification-evidence.json`: input, script and artifact checksums; actual ET completion stamp; no approval granted.

| Measurement | Result | Meaning |
|---|---:|---|
| Concept definitions measured | 8,495 | Their row counts sum to every one of the 5,134,979 observations |
| Companies per concept | 1–319 | No one reported concept covers all 329 Companies |
| Concepts seen in one Company | 2,248 | Standard line items need measured mapping coverage, not a universal-concept assumption |
| Concepts spanning multiple observed end-date years | 7,965 | Calendar-year coverage of captured observations; not a claim of comparable annual periods |
| Missing or unparseable period ends | 0 | All observed end-date years can be counted; business-period interpretation remains ticket 35 |
| Company/concept/unit/start/end groups | 2,727,545 | Taxonomy is included in concept identity |
| Groups occurring in multiple filings | 1,438,975 | Filing versions must be distinguished before analytical selection |
| Repeated-filing groups with differing derivative values | 139,978 | Not all are verified restatements; this count uses the existing DOUBLE derivative |
| Rows in repeated-filing groups | 3,846,409 | Repetition across filings is expected evidence, not an instruction to discard rows |
| Duplicate eight-column candidate keys | 0 | CIK, taxonomy, concept, unit, start, end, accession and filed date identify every observed row in this snapshot |
| Exact duplicate rows | 0 | No fully identical row was found across the derivative's thirteen columns |

The candidate key's uniqueness is observed in this delivery only. Persistence across deliveries, absent values, conflict handling, source ordinals and the silver grain still need their own decisions/tests. These counts include every captured form and period: they do not select annual line items, choose latest/first values, align fiscal years or prove MDM links.

No local MDM connection is configured in the current environment, and no master snapshot exists under the permitted Company facts capture. Consequently the 100% CIK link above proves the captured Company list only. Existing MDM Company lookup coverage is explicitly unknown and needs the local lookup proof, not a production query or a guessed master id.

### Original capture authentication and precision boundary

The local capture ledger has 500 cohort entries: 368 captured responses and 132 no-facts responses, with no other status. Every captured file's decompressed SHA-256 and byte length match its ledger entry: 772,842,970 raw bytes and 50,936,828 compressed bytes. Of the 368 documents, 329 contain facts and 39 contain none. All 329 fact-bearing document CIKs match their filenames. Raw observation counts reconcile exactly to the derivative's 5,134,979 rows.

The original JSON contains 4,811,345 integer tokens and 323,634 decimal/exponent tokens. One integer changes under DOUBLE conversion; it exceeds both signed and unsigned 64-bit integer ranges. Its value, file, checksum and observation position remain private in `precision-case.json`. The capture receipt evidence is `raw-capture-authentication.json`; the exact executed scripts are retained beside the private findings. This authenticates the inputs and identifies a numeric boundary; it does not qualify a production reader or approve any numeric coercion.

Tickets 40, 44 and 45 must use the original captured evidence for the reading decision, answer key and exact-number qualification. The known exceptional integer needs an explicit tested handling path; the existing long-form value cannot stand in for its original number. The documented 64-bit guarantee in data-platform `READING.md` is not proof for this out-of-range case. Any required engine change remains its own ticket and PR, after the reading decision; none is inferred here.

## Progress review

### Standards

Dedicated fresh ticket branch/worktree; evidence contains only counts and schema vocabulary. Raw captures and full profiling findings stay outside the public repository. No provider request, production change or overlap edit.

### Spec

This is a checkpoint, not a completed ticket: the unchecked checklist items remain pending. No operator answer or findings approval has been inferred.

### GoF

The refactor-review skill is available; this checkpoint changes no program code and introduces no design-pattern refactor.
