# Run a Proving Run on a pinned SEC + GLEIF cohort

Type: task
Status: claimed (Claude, branch `claude/company-mastering-05-proving-run`, 2026-09-26 11:00 ET)
Blocked by: 04's identifier rules and 08's matching rules, both built (Claude, 2026-09-26: the Proving Run is rolled back and publishes nothing, so it does not wait for the operator's answers in ticket 15 on suspension; its counts can inform them)

## Question

Report what the rules **would** decide on real evidence, publishing nothing
and activating nothing.

- Pin the cohort first: a frozen CIK manifest (Company Q3) plus the verified
  GLEIF publication already captured. The old 308 adjudicated links are not
  independent truth; they may be read only as a comparison.
- Run the policy over it inside a transaction that is rolled back, or into a
  candidate-only store, so no master state changes.
- Report per record: bound, deferred, no candidate, conflicting; with the rule
  and evidence for each, and the counts Company Q12 needs to call the milestone
  complete or incomplete.
- State plainly what the run does **not** establish: it is not activation, not
  a rebuild approval, and not a precision qualification for a fuzzy rule.

## Plan (Claude, 2026-09-26 11:00 ET)

The spec's order: "For large sources run a bounded sample first, then the
resumable full build" (`acceptance.md`). The next gate, ticket 06, approves
the digest of the **CIK matching rule**. Under Q14 that rule needs a verified
Identifier Contract, not a precision study, and it reads no Name Census.
Only the two name rules read the census, and their switch-on waits on
ticket 13. So the run comes in two phases.

**Phase 1: the CIK matching rule over every SEC Company (this branch).**
The production path, unchanged: `bootstrap-batch` capture, `name-census`,
`prepare-clean-company`, and the Merge Stage on a disposable PostgreSQL 16
with the restricted runtime role.

Why seven captures: `prepare-clean-company` takes at most 1,000 records,
and only from the head of one capture. And the census must count that same
capture, so it counts only the capture's own filers. A census that small
understates how many SEC filers share a name. That is harmless here,
because no active rule reads it, but it makes name-rule numbers from this
run worthless. They are not reported.

Checklist (times ET):

- [ ] **Freeze CIK manifest v1** (a reversible technical choice, Claude):
  - the population is ticket 12's frozen cohort of 76,230 bronze filers,
    with each filer's object key from the ticket 08 scan;
  - the cohort is the 6,414 filers the active Company rule
    (`sec-company-candidate` 2026-09-25.13) calls a Company, plus 586
    seeded non-Company controls, Tim Cook and Satya Nadella among them;
  - it is dealt into seven chunks of 1,000;
  - the seed and SHA-256 are recorded.

  The 308 adjudicated links are not used.
- [ ] Copy the 7,000 submissions documents from prod bronze, with S3 reads
  only, and hash each one.
- [ ] Land SEC's ticker catalog from bronze through the production writer
  (`_parse_company_ticker_rows`, `SilverLandingStore.replace_company_tickers`,
  `write_landing_export`). This needs no network, because
  `_sync_reference_data` lands tickers only after a fresh SEC download.
- [ ] Capture each chunk with `bootstrap-batch` behind a dead proxy with
  blocked AWS keys. Show that no SEC request was made and no bronze object
  was written.
- [ ] For each chunk, build a census and a bundle with the production
  commands.
- [ ] **The candidate policy:**
  - the approved Company policy plus the CIK matching rule
    (`company-cik`), its Identifier Contract and a deterministic
    activation, under a named version;
  - the contract's verification evidence is the manifest;
  - the Proving Run registers a copy stamped "Proving Run, not an
    approval". The body the operator is asked to approve differs from it
    only in those three approval fields.
  - `983352e8…4049` is unchanged.
- [ ] Apply all seven bundles, then apply them again. The second pass must
  create no new Company.
- [ ] **The report:**
  - each record's outcome: Company or waiting, and new Company, joined,
    conflict or suspended, with the rule;
  - CIK uniqueness;
  - where production classification differs from the research labels;
  - what the run does not establish.

**Phase 2: the whole population and the name rules (a later slice).**
- A resumable whole-population preparer: a CIK manifest with offset and
  count, as the native GLEIF batches have.
- One full capture, with filing rows measured for scale, and a census over
  it.
- The GLEIF publication, and name-rule outcomes.

This is production code, so it needs `/gof-refactor-reviewer`, TDD and
review. It gates Company Q12 and the name-rule approval, not ticket 06.
