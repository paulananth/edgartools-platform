# Run a Proving Run on a pinned SEC + GLEIF cohort

Type: task
Status: Phase 1 done (Claude, branch `claude/company-mastering-05-proving-run`, 2026-09-26 12:53 ET); Phase 2 open
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

- [x] **Freeze CIK manifest v1** (a reversible technical choice, Claude):
  - the population is ticket 12's frozen cohort of 76,230 bronze filers,
    with each filer's object key from the ticket 08 scan;
  - the cohort is the 6,414 filers the active Company rule
    (`sec-company-candidate` 2026-09-25.13) calls a Company, plus 586
    seeded non-Company controls, Tim Cook and Satya Nadella among them;
  - it is dealt into seven chunks of 1,000;
  - the seed and SHA-256 are recorded.

  The 308 adjudicated links are not used. Done 2026-09-26 11:01 ET:
  `research/05-manifest.json`, sha256 `3607ae6c…60cc`, seed `20260926.05`
  (`05-manifest.py`; a rerun reproduces it).
- [x] Copy the 7,000 submissions documents from prod bronze, with S3 reads
  only, and hash each one. Done 11:04 ET (`05-copy-bronze.py`): 7,000
  documents, 638 MB, plus the ticker catalog `836140c5…`. After all seven
  captures, all 7,001 copies still match their hashes.
- [x] Land SEC's ticker catalog from bronze through the production writer
  (`_parse_company_ticker_rows`, `SilverLandingStore.replace_company_tickers`,
  `write_landing_export`). This needs no network, because
  `_sync_reference_data` lands tickers only after a fresh SEC download.
  Done 11:05 ET (`05-land-tickers.py`): 10,391 ticker rows.
- [x] Capture each chunk with `bootstrap-batch` behind a dead proxy with
  blocked AWS keys. Show that no SEC request was made and no bronze object
  was written. Done 11:08–11:24 ET, about 90 seconds each (a fresh local
  bookkeeping database):
  - there are no proxy errors or tracebacks;
  - the only new files are each run's own manifests under `bronze/runs`
    and `bronze/reference/cik_universe`;
  - the largest filings member is 22 MB, under the preparer's 64 MB limit.

  **Finding:** the capture lands no Company row for an SEC `other` filer
  that the warehouse reads as an individual. In chunk 1 that is 34
  controls. Every Company landed.
- [x] For each chunk, build a census and a bundle with the production
  commands. Done 12:42 ET (`05-bundles.sh`):
  - about 25–31 minutes per census, which streams the full 3.4-million-record
    GLEIF copy;
  - 6,726 records are prepared;
  - the 274 CIKs not prepared are all controls that the capture landed no
    Company row for (SEC `other` filers read as individuals).
- [x] **The candidate policy:**
  - the approved Company policy plus the CIK matching rule
    (`company-cik`), its Identifier Contract and a deterministic
    activation, under a named version;
  - the contract's verification evidence is the manifest;
  - the Proving Run registers a copy stamped "Proving Run, not an
    approval". The body the operator is asked to approve differs from it
    only in those three approval fields.
  - `983352e8…4049` is unchanged.

  Done: `research/05-candidate-policy.json`, version
  `company-2026-09-26.cik-matching-rule`, digest **`36637a09…bbba`**. Its
  tolerance line is the spec's `sec.cik` row, which the spec wrote for a
  Person (`warm_up_decisions` 10,000, `max_per_10k` 5). With a
  `kind_equal@1` compatibility check, its name-mismatch alarm may never fire
  for a Company. The operator should know this at ticket 06. The copy the run registered is `d90fa391…b655`.
- [x] Apply all seven bundles, then apply them again. The second pass must
  create no new Company. Done 12:11–12:53 ET: passed, and the second pass
  changed nothing.
- [x] **The report:**
  - each record's outcome: Company or waiting, and new Company, joined,
    conflict or suspended, with the rule;
  - CIK uniqueness;
  - where production classification differs from the research labels;
  - what the run does not establish.

  Done: `research/05-summary.json`, and `research/05-outcomes.jsonl` with
  one line per CIK. The results are below.

**Phase 2: the whole population and the name rules (a later slice).**
- A resumable whole-population preparer: a CIK manifest with offset and
  count, as the native GLEIF batches have.
- One full capture, with filing rows measured for scale, and a census over
  it.
- The GLEIF publication, and name-rule outcomes.

This is production code, so it needs `/gof-refactor-reviewer`, TDD and
review. It gates Company Q12 and the name-rule approval, not ticket 06.

## Phase 1 results (Claude, 2026-09-26 12:53 ET)

The run used the production path end to end:
- 7,000 CIKs, 6,726 records prepared, on a disposable PostgreSQL 16 under
  the restricted runtime role;
- zero SEC requests, and no bronze document changed.

| What happened to each CIK | Count |
| --- | --- |
| A Company by the CIK rule (research label: Company) | **6,414 of 6,414** |
| Held in the Stage by the Company rule (research label: control) | 312 |
| No Company row landed by the capture (research label: control) | 274 |
| A control that became a Company | **0** |
| A Company the research named that did not become one | **0** |

- **One Company per CIK.** No CIK sits on two Companies, and no Company
  holds two SEC records. There are 6,414 identities, 6,414 open Company
  versions and 6,414 bind decisions.
- **The four named Companies:** Apple, Microsoft, Shell and ASML each
  became one Company by their CIK.
- **The named controls:** Tim Cook and Satya Nadella have no Company row at
  all. The capture reads them as individuals.
- **Idempotent.** Applying all seven bundles again changed no count.
- **No review other than the Company rule's.** The 312 open reviews are all
  `classification_deferred`. There are none for an ambiguous, conflicting
  or suspended identifier, so the two questions in ticket 15 did not arise
  in this cohort.
- **The held-back records, by the Company rule's step:**
  - 295 wait at step 11, the rule's last step, with no Probable Kind;
  - 8 at step 1;
  - 2 at step 7 and 2 at step 7b (Probable Kind: Company);
  - 2 at step 9 (Probable Kind: Person);
  - 1 each at steps 2 and 5 (Fund) and step 3 (Government).

  By SEC entity type, 284 are `other`, 15 `investment` and 13 `operating`.
- **The capture filter.** The 274 records not landed are all SEC `other`
  filers that the warehouse reads as individuals, so they never reach the
  Company rule. No Company in the cohort was lost this way, but some names
  do not look like people ("Control Empresarial de Capitales S.A. de C.V.",
  "BMA VIII L.L.C."). The filter decides before any rule does, and no
  proof measures it. Recorded as fog on the map.

### Found: one SQL function takes 91% of the Merge Stage's time

The run switched on per-function timing (`track_functions`).
`mdm_v2.company_payload_from_table` (migration 037, called by the
publication trigger `publish_company_authority`) took:
- **1,639 of the 1,796 seconds** spent in the batch commit;
- 42 calls, about 39 seconds each.

Its loop appends each publication object to a JSON array
(`rebuilt := rebuilt || jsonb_build_array(item)`). Each append copies the
array built so far, so the cost likely grows with the square of the batch
size. That comes from reading the code; it has not been timed at several
batch sizes.

A batch of about 960 records took 183–357 seconds, about 3–6 minutes
depending on the CPU the censuses were using. The operator chose to remove the
cause, not tune it (2026-09-26 13:03 ET): a Company is kept in one place,
the dated Company table, and the copy steps go. That is
[Keep each Company in one place](17-keep-each-company-in-one-place.md),
ticket 17, on its own branch.
At today's speed, Phase 2's whole population (77 batches) would take about
four to eight hours.

### Found: a Company a rule creates cannot yet be undone

`identity.replay` refuses to move an established binding ("requires a
correction contract"), and `revoke` reaches only overrides, exclusions and
reversals. So once the CIK rule is switched on, a Company it creates stays,
even if the Company rule had mislabelled the record.

The Company rule's measured lower bound is 99.11% per step at 95%. At that
bound, up to about 57 of 6,414 Companies could be mislabelled. The point
estimate is 0: 600 of 600 in the sample, 0 of 328 adversarial.

Ticket 13 builds a correction contract, but only for name-rule links. The
operator should weigh this at ticket 06.

### What this run does not establish

The ticket asks for this plainly.

- **It is not activation.** Nothing was registered in a shared store, and
  no rule is switched on. The run used a disposable PostgreSQL 16 that no
  longer exists.
- **It is not the operator's approval.** The copy the run registered is
  stamped "Proving Run, not an approval". Approval is ticket 06. The digest
  the operator is asked to approve (`36637a09…bbba`) is the body with its
  three approval fields empty. After approval, those fields hold the
  operator's name, time and reason, so the active digest will differ. It
  is shown again for a final review, as ticket 12 did.
- **It is not Company Q3 or Q12.**
  - The cohort is the 6,414 Companies of ticket 12's frozen bronze
    population, not a CIK manifest the operator approved.
  - The run holds no GLEIF record, so no Company gains an LEI. Q12 needs
    qualified multisource matching, which is Phase 2.
- **It says nothing about the name rules.** Each chunk's Name Census
  counts only its own capture of about 960 filers, so any name-rule result
  from it would be falsely optimistic. The name rules are not switched on
  in the candidate policy, and none of their numbers are reported.
- **CIK uniqueness is shown within the 7,000 CIKs only.** It is not shown
  across all 76,230 filers. A CIK is SEC's own key and each bronze
  document is keyed by it, but the run did not test the whole population.
- **It is not a precision study.** Under Q14, identifier-only binding needs
  a verified Identifier Contract, not a statistical bar. The run is that
  contract's verification evidence.
