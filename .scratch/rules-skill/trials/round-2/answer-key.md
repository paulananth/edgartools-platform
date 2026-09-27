# Round 2 answer key: record-based answers only

Each answer below is a decision or a fact from the written record. It is
never a file path or a copied mapping value. Questions that were not asked
are not volunteered.

## Both sources

- **Registered or new:** not registered; treat it as new, keeping the names
  the repo already uses (pass bar, ticket 07).
- **Approval:** never answered. The trial stops at approval.

## SEC submissions

- **Scope:** Companies only. Individual filers are out of scope, and the
  warehouse already drops them.
- **Kind:** decided by the approved Mastering Policy rule for SEC Company
  candidates, not by `entityType` (ticket 12). *Should have inferred* from
  `rules/merge/policy.yaml`.
- **State of incorporation vs jurisdiction:** SEC's value stays SEC's own
  field, written as SEC writes it. Jurisdiction is GLEIF's, so the two never
  compete (operator, 2026-09-24).
- **Address:** the business address, not the mailing address.
- **SEC's stated LEI:** not an identifier path. It is filled for 392 of
  76,230 filers, and 4 of them are operating companies (company-mastering
  remaining work, item 2). Do not map it.
- **EIN, tickers, former names:** not Company fields today. Tickers feed
  only the Company rule; that rule reads them from the reader's record.
- **Matching values:** the SEC-to-GLEIF matching rules compare the business
  postcode, the business country and the Name Census entry. They are kept
  with the record, out of its fields (ticket 08). *Should have inferred* from
  `rules/merge/kinds/company.yaml`.
- **Data defects** (ticker duplicates, the `P7` region, ICONIQ dropped as an
  individual): out of scope for the rules file; recorded in company-mastering
  ticket 18.

## GLEIF

- **Scope:** Level 1, relationships and reporting exceptions (GLEIF ticket
  16, first delivery slice).
- **Kinds:** GENERAL is a Company. FUND, BRANCH, resident government entity
  and international organization are recorded only as what the record
  probably is, and none creates an identity. A sole proprietor is left
  unnamed: it is not settled as Person.
- **Relationships:** only direct and ultimate accounting consolidation. The
  branch and the three fund relationships stay as captured source evidence;
  they are not mapped into Company (GLEIF ticket 10).
- **Name and jurisdiction:** `name` is shared with SEC, and SEC wins where
  both give one. `jurisdiction` is GLEIF's alone (operator, 2026-09-24).
- **What does not block a run:** records outside the approved Company scope,
  records of a kind MDM does not take yet, and valid reporting exceptions.
  Malformed LEIs, unknown kinds and source integrity problems do block
  (native GLEIF operation, migration 030). A question on the bad check digit
  *should have been inferred* from the skill's "a defect always blocks".
- **Matching values:** the matching rules compare the headquarters postcode
  and the headquarters country (ticket 08).
- **Deletion field, "NULL" statuses:** recorded in company-mastering ticket
  18; no change to the rules file.

## SEC phase A: questions asked and how each was tagged (2026-09-26)

| # | Question | Tag | Answered from |
|---|---|---|---|
| 1 | Are these SEC submissions files plus both ticker lists? | real (the confirmation the skill requires) | — |
| 2 | Is `sec.submissions.company.v1` registered, and with what mapping? | command gap (`rules status` not built) | pass bar: not registered, treat as new |
| 3 | Do held-back filers wait quietly, or block? | real operator decision (still open) | ticket 12: "wait in the Stage" was recommended, not decided; migration 027: deferred records block |
| 4 | Should SEC's business address fill `address`? (it recommended no) | should have inferred: the merge rules rank this source for `address` | operator 2026-09-24 10:00 ET (ticket 09) |
| 5 | Leave out EIN, phone, website, tickers, former names, LEI? | **real operator decision**: my first tag ("should have inferred") was wrong | operator, 2026-09-26 ~19:35 ET: "must be on mdm for cross reference id for lookup any document only with ids keep ein, tickers, lei". Phone, website and former names stay out. Sent to the agent as a correction during phase B. Open: whether any of them may join records |

Skill gaps from SEC phase A (to fix after round 2):
- A known source whose rules file is missing fits neither "add" nor "change", and the "not new" branch skips profiling.
- Find the reader through code that loads the source's rules file or names its source code, not through the `normalize` caller (SEC's is generic).
- Profile the reader's record shape, not only the raw files, and say how to build it without a warehouse load.
- Where the registered version names live (`rules status` gap).
- `bronze.family` names one family; tickers come from a second (`reference_catalog`). No code reads `bronze`.
- The language cannot map former names to aliases (a language gap, for the operator).
- `edgar-warehouse rules --help` "hung": checked 2026-09-26 19:3x ET, it is not a hang. The CLI takes 26 s just to reject an unknown command (heavy imports at start-up), and longer with bytecode writing off. When the `rules` commands are built, load them lazily and keep `rules --help` fast.
- A field the merge rules rank for this source is one the source supplies; the skill should say so.
- ~~Do not ask about leaving out fields MDM does not have~~ withdrawn: the operator wants identifiers kept even when MDM has no field for them. The skill should ask about every identifier the source carries.

Operator follow-ups to SEC Q5 (2026-09-26 evening): lookup only, never join records; SEC LEI under its own name; tickers belong to the Security entity, not Company (ticker lists: a Security mapping later, needs a CUSIP link).

## GLEIF phase A: questions asked and how each was tagged (2026-09-26 ~19:50 ET)

| # | Question | Tag | Answered from |
|---|---|---|---|
| 1 | Golden Copy full files, 2026-09-11 16:00 UTC? | real (the confirmation the skill requires) | — |
| 2 | Is any GLEIF source registered? | command gap (`rules status`) | pass bar: treat as new |
| 3 | Source names, plus a fourth publication contract? | names: should have inferred (they match `gleif.level1.v1`); fourth: real gap (the publication contract has no home in `rules/`) | the proven file comment: three members, one contract each |
| 4 | Capture family name? | should have inferred (the folder the reader loads is `gleif`) | GLEIF ticket 09: one shared capture |
| 5 | Where the approved Company LEI list comes from | **real open design gap**: `company_leis` lives in the publication-level native contract, which only tests build today | GLEIF ticket 16: "manually approved or deterministic Company-to-LEI source links" |
| 6 | Add the relationship source to Company's source list? | real (a merge-rules change needs approval); the claim needs checking | not changed in the trial |
| 7 | Legal or HQ address in `address`? (it recommended neither) | real record conflict: GLEIF ticket 15 said "separate initially", and the operator's 2026-09-24 decision (company-mastering ticket 09) made address one field. **The skill should say the later operator decision wins.** | operator 2026-09-24 10:00 ET |
| 8 | Legal-form code or text? | minor real | GLEIF ticket 15: "legal form" |
| 9 | 356 bad check digits and 422 rejected relationships: keep them blocking? | real (the reader fixes are in company-mastering ticket 18) | ticket 18, items 2-3 |

New finding for ticket 18: the Level 1 zip is 928 MB against the reader's 1 GiB cap, so a later Golden Copy may not fit.

Skill gaps from GLEIF phase A (to fix after round 2):
- The missing-rules-file case again (same as SEC).
- REFERENCE omits rules the reader enforces: `schema_version` = `adapter.version`; `family` = the capture family; `publication_families` includes the reader's family; `classification` is refused for native members. The skill should say to read the reader's validation code for such rules.
- The publication-level contract (`native_contract`: record sources and the approved list; `publication_contract`) is not described anywhere.
- A relationship's `scope` is fixed text, not a path.
- A Company source missing from `defaults.sources` fails its batch (to verify); a relationship needs its own match before it becomes a link.
- The reader's check order can make defects block outside scope.
- Sample from the start, middle and end of a sorted file, not just the first 10,000 records; give a fallback when a full pass is too slow.
- When records disagree, the later operator decision wins (fixes Q7).
- A source's documentation is separate from its data API: never call the data API.
- "Never guess an identifier" also covers a required list of approved identifiers.
