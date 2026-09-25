# Company mastering: remaining work

Created 2026-09-24 21:55 ET at the operator's request. Kept current per the
task-checklist rule (CLAUDE.md): tick a line with the ET time and how it was
verified. The end state is the [completion gate](../../docs/specs/clean-mdm/company-completion.md):
**one master record per real Company, holding its CIK from SEC and its LEI
from GLEIF**, decided by approved rules, proven locally on real PostgreSQL 16.

Already done: tickets 01–04, 07, 11; parts of 09 (Company rule as data, source
priority SEC then GLEIF, every field from every source).

## 1. SEC Company rule: Shell and ASML become Companies (ticket 12, PR #712)

- [x] Bar per decision type; Company classification requires a 95% one-sided
  lower bound at 95% confidence (operator, 2026-09-24).
- [x] The old Legal-form rule failed a fresh adversarial draw (18 Funds in its
  step-2 arm); its proof and approval were withdrawn (2026-09-24 22:21 ET).
- [x] The Account hold-back replaced it and passed its frozen bronze-based
  labels: 600/600 sampled Company calls, each Company step 300/300 with a
  0.9911 lower bound, and 0/328 adversarial violations (2026-09-25 08:13 ET).
- [x] The pending rule stays inactive while tests pin its exact digest;
  focused tests, three repaired PG16 tests, Ruff, and the new CI re-score
  pass (2026-09-25 08:33 ET).
- [x] Full PostgreSQL 16 Clean suite: 134 passed without skips in 6m42s;
  all seven PR #712 CI checks green; Standards/Spec findings repaired and GoF
  review recommends no refactor (2026-09-25 08:37 ET).
- [x] Operator approved the frozen Account hold-back proposal fingerprint;
  the reply was processed at 2026-09-25 13:09:33 ET.
- [x] The approved rule is active on the Codex branch. The active policy
  fingerprint is pinned; all five four-company PG16 tests pass (2026-09-25 13:12 ET).
- [x] Full local suites on the active rule: 1,573 MDM/architecture and 134
  PG16 Clean tests passed without skips (2026-09-25 13:21 ET).
- [ ] PR #712 CI on the active rule; check its final fingerprint before
  registration, then merge only on the operator's word.

## 2. Match SEC and GLEIF records into one Company (ticket 08) — critical path

- [x] Measure how often SEC's own record states its LEI (2026-09-24 22:24 ET): 392 of 76,230
  filers (356 valid), 4 `operating`; not an identifier path. GLEIF authority
  `RA000665` (IDs that are CIKs) is SEC's authority for registered funds, 57
  of 7,130 Companies. Neither source joins Companies (ticket 08 branch,
  `research/08-sec-lei-and-gleif-sec-authority.md`)
- [ ] The name/country/address shape measured 85.6–93.1% before (below 95%):
  find a stricter rule (uniqueness both ways, GLEIF GENERAL only, legal form,
  postal code and street number), tuned on the 883 reviewed pairs
- [ ] Matching rule for the rest: name, country and address (operator's first
  choice); ticker/CUSIP/ISIN later as corroboration
- [ ] Measure it per rule step at the 95% bar; 50–95% waits in the Stage,
  below 50% goes to a Steward
- [ ] Operator approves the matching rule's fingerprint
- [ ] Apple, Microsoft, Shell, ASML each end as **one** master with CIK and LEI

## 3. The dated Company table, the final authority (ticket 09)

- [ ] Decide the identifying-field columns
- [ ] Decide what `valid_from` means (source change time, or MDM's decision time)
- [ ] Address as one field (SEC's address table is not yet read)
- [ ] Refuse a policy source name that matches no registered source
- [ ] Settle the GLEIF source name (`gleif.lei.v1` vs `gleif.level1.v1`)
- [ ] Policy file changes without a code release
- [ ] Stores holding readings under the old field names
- [ ] Migration, Merge Stage writes the table in the same transaction, tests on
  a populated store; remove the `company_master` view

## 4. Stage holds only the latest record per source (ticket 10)

- [ ] What a match decision points to once the record it named is replaced
- [ ] Reversal and replay re-read bronze instead of kept Stage rows
- [ ] Field provenance after a replacement
- [ ] Lift the append-only guard on the Stage; migration on a populated store;
  merge runs at the end of each source load

## 5. Matching-rule safety items left from ticket 04

- [ ] Suspended identifiers hold a record back (needs ticket 03's suspension list)
- [ ] Re-check, just before saving, that the Company a record joins is still valid
- [ ] An assessment left behind by a crash between assessment and save
- [ ] A new Company's publish time comes from the caller's as-of time
- [ ] A real two-runs-at-once concurrency test

## 6. Whole Proving Run and final approval (tickets 05, 06)

- [ ] Pin the cohort (frozen CIK list plus the captured GLEIF publication)
- [ ] Run every rule over it with nothing published: bound, waiting, no
  candidate, conflicting, per record, with the rule and evidence
- [ ] Operator approves the final policy fingerprint

## 7. Completion gate items not yet started

- [ ] Company relationships: GLEIF accounting parents (direct, ultimate), dated,
  kept separate from ownership; cycles and conflicts reviewed
- [ ] Updates: GLEIF daily delta, monthly full reconciliation, gap recovery;
  changed, retired and successor LEIs re-checked
- [ ] End to end: API shows source evidence and field provenance; export and
  graph publish the same generation; lost acknowledgements, reordering,
  duplicates, corrections and retirements keep exact results
- [ ] Reverse a wrong merge; quarantine what a rule cannot fix

## 8. Records waiting for other kinds or later rules

- [ ] Fund kind: SEC `investment` filers, exchange-traded commodity trusts
  (SIC 6221), private funds (e.g. Stonepeak-Plus); BDCs stay Companies and may
  get a Fund profile
- [ ] Government Body kind: foreign governments (SIC 8888)
- [ ] Loan trusts (SIC 6189): decide their kind
- [ ] About 120 annual reporters with no SEC filer category (e.g. Royal Bank of
  Canada) wait; a later rule step for them
- [ ] "Matching rule" in the `CONTEXT.md` glossary, after Grok's uncommitted
  edits there land

## 9. Warehouse items that feed v2

- [ ] A trust or LLC filing only Schedule 13D/13G, with no industry code or
  ticker, is taken for a person (`is_individual_filer`)
- [ ] Restore the 1,658 CIKs wrongly marked as people (production; deferred)
