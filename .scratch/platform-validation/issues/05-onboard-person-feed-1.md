# Onboard Person feed 1 (SEC individual filers) with Data Onboarding

Type: task
Status: merged as #770; switch-on (`rules activate`) waits for a Clean MDM database

## Operator rulings

- "can we onboard another domain like person by listing the feeds";
  "Person as the skill's test here" (2026-09-30).
- "continue with slice 3 complete testing and creating person" (2026-10-01).
- Rule C-J for reporting-owner classification: "agreed" (2026-09-20,
  person-consumer-contract ticket 03, on research 18's numbers).

## What this is

Feed 1 is the SEC submissions document of each individual filer: the
same files the Company source reads (`sec.submissions.company`), read a
second time for the Person kind. The CIK is the identifier, so joining a
record to its Person is deterministic. It is the Data Onboarding skill's
real test: every mode is walked as written, and each gap is fixed in the
skill or ticketed.

Log: `.scratch/onboarding/sec.submissions.person/onboarding-log.md`.
Starting point: the round-2 trial drafts
(`.scratch/platform-validation/trials/round-2/data-onboarding-person/`).

## Checklist

Session 2026-10-01 06:55-07:12 ET ran under the operator's rule "no coding,
only configuring". Every step that needs code is a SKILL-GAP in the log.

- [x] identify: name, source code, family, new domain (from the trial,
  checked again). Verified against `receipts.jsonl` (76,230 documents plus
  1 ticker file) and a repo search (2026-10-01 07:00 ET)
- [ ] ~~profile: all 76,230 files of the pinned capture~~ deferred to a
  `rules profile` ticket (rules-skill 06): it needs a script (SKILL-GAP 7).
  Grep counts only (entityType, ein, lei, formerNames, empty names), in the log
- [x] map: `rules/sources/sec.submissions.person/source.yaml`. Copied from
  the trial, comments corrected; loads in `rules mapdoc check`, exit 0
  (2026-10-01 07:06 ET). The `files.source` round-trip was not run (SKILL-GAP 6)
- [x] quality: `quality.yaml`. One check, touching 0 of 76,230; loads in
  `mapdoc check` (2026-10-01 07:06 ET). `on_fail: exception`, agreed by the operator (Q5 "yes")
- [ ] metadata: Mapping Document and catalog entry. Generated: `mapdoc write`
  for the source and the kind, `mapdoc check` exit 0, `catalog plan` exit 0
  (2026-10-01 07:07 ET). Steward agreement: Q6 "yes". Not done: the workbook
  bugs (SKILL-GAP 10), feed lineage (SKILL-GAP 11), publish (after merge)
- [x] Merge rules: `rules/merge/kinds/person.yaml` (CIK matching rule).
  Rules are byte-identical to the scored draft; loads in `mapdoc check`
  (2026-10-01 07:06 ET). Nothing added to `automatic_rules` (git diff)
- [x] Classification proof, first version: the ported rule scored against
  research 18's 1,380 labels (841/841, 0.995453) (2026-10-01 07:05 ET).
  Superseded by the fresh-sample proof below (570/570, 0.993305), which
  `pending-proofs.yaml` and `policy.yaml` carry
- [ ] ~~Population check: the people the rule finds that never filed a Form
  3/4/5 (outside research 18's population)~~ deferred: it needs a pass of the
  rule over all documents, which is code (SKILL-GAP 5)
- [x] Operator questions Q1–Q11 answered and recorded in the log with the
  operator's words (2026-10-01 about 07:40 ET)
- [x] Fresh sample drawn and labels drafted (Q7; Q12 "Agreed": 570 people
  plus 150 others, seeded draw, research 18 excluded); labelling agents blind
  to the rule (2026-10-01 08:05 ET)
- [x] Rules tested against the draft labels: person 570/570 (lower bound
  0.99331), entity 102/102; no adjustment needed (log, "Fresh-sample test")
  (2026-10-01 08:11 ET)
- [x] Operator checked the 6 uncertain sample labels: all person, so the
  person step stays 570/570 (`operator-checks.jsonl`) (2026-10-01 08:51 ET)
- [x] Labels done: the operator checked 100 sample rows and 43 hard cases in
  batches, then accepted the other 612 on their words ("only ask the real
  harder once"); screened for hard signs, none found (2026-10-01 about 09:00 ET)
- [x] `pending-proofs.yaml` holds the fresh proof: 570/570, lower bound
  0.993305, adversarial fixture `hard-cases-checked.jsonl` (57, 0 entities
  called a person). No approval. `rules pending` needs `RULES_DATABASE_URL`
  (Q10), so the strict loader has not read it yet (2026-10-01 about 09:01 ET)
- [x] Code ticket 05a, the pinned tests and the shared CIK count: PR #769,
  merged on the operator's "Yes" (2026-10-01 09:27 ET)
- [x] Hard-case set drafted and scored: 57 real filers, 0 entities called a
  person, 1 person called an entity (HOLDING FRANK B JR), 34 held back; no
  adjustment (log, "Hard-case set") (2026-10-01 08:39 ET)
- [x] Operator checked the 8 uncertain hard cases the rule decides: 7 person,
  1 entity (a trust); still 0 entities called a person (`operator-checks.jsonl`)
  (2026-10-01 about 08:46 ET)
- [ ] ~~Operator ruling: "there has to be relationship along with mdm it can not
  be separated"~~ moved to slice 6 (`06-relationship-rules.md`). Feed 1 cannot build a link (one CIK per document); the
  relationship requirement goes to the next Person feed ticket, which must
  master people, entities and the person–role–entity links together
- [ ] ~~Hard-case set, about 50 real filers (Q8 "yes"): agent drafts, the
  operator checks, the rule is scored on it before switch-on ~~ done above
- [ ] ~~Treat EIN 000000000 as empty~~ deferred to a later Refining Rules
  version (Q11 "yes"), re-scored before switch-on
- [x] Set-aside records: do company files read as Person block the feed? No.
  Read in `adapters.py`: step 1 raises `classification_deferred`, which is
  listed as non-blocking (2026-10-01 07:02 ET)
- [ ] ~~Dry run (`normalize`) over all files: accepted, set aside, by
  reason~~ deferred: needs code (SKILL-GAP 1)
- [ ] ~~Proving run on a disposable PG16: small first, then full, twice
  (second pass unchanged)~~ deferred: needs code and Docker (SKILL-GAP 2)
- [x] Proving run script `proving_run.py`, the code exception the operator
  allowed ("Yes", 2026-10-01). It stands in for a Person reader, and
  `person-cik` is switched on as a Proving Run activation. Small run, 300
  documents: 49 Persons, 251 set aside, 0 CIKs on two Persons, 0 overlaps
  with the Company cohort, second pass unchanged (2026-10-01 09:52 ET)
- [ ] ~~Full proving run over 76,230 documents, twice~~ deferred to
  `05b-match-proposal-snapshot-scaling.md`: replaced by a 10,000-document
  cohort plus a database-free population pass. Started 09:53 ET:
  - the harness stopped it at about 25 minutes, its limit for background
    commands, so it was restarted detached at 10:19 ET;
  - that run stalled at batch 70 (`match_proposal_snapshot` slows down as
    the store grows: ticket `05b-match-proposal-snapshot-scaling.md`);
  - restarted at 11:36 ET with every reading applied before the set-aside
    records; still about 5 minutes per 1,000 Persons (05b);
  - restarted at 12:24 ET on a seeded random cohort of 10,000 documents (as
    Company's ticket 05), plus a database-free pass over all 76,230.
- [x] `rules save` and `rules record-proof`, on the local Rules Database (2026-10-01 18:12 ET)
- [x] Approval 1, the classification rule `sec-person-candidate`: operator
  "Approved"; `rules approve --rule` wrote it into `policy.yaml` (2026-10-01
  09:39 ET)
- [x] Proving run passed (2026-10-01 13:50 ET, 32 min 40 s):
  - seeded cohort of 10,000: 4,044 Persons by CIK, 0 duplicates, second pass
    unchanged;
  - population of 76,230, rule only: 31,097 people;
  - 0 CIKs both a Person and a Company (the 4 overlaps are Company's controls).
- [x] Approval 2, `person-cik` and its CIK Identifier Contract: operator
  "Approved". The verification stamp and `automatic_rules` entry were written by
  hand as for `company-cik`; `check_policy` passes (2026-10-01 17:12 ET)
- [x] Two activation tests fixed, with the operator's "yes" (code). They
  assumed only Company's rules were switched on. 92 passed with and without
  Person's rules; the other pinned files pass; `rules mapdoc check` exit 0
  (2026-10-01 18:08 ET)
- [x] Local throwaway Rules Database (operator: "no login needed"): `rules
  init`, `save` and `record-proof` for the merge rules (2026-10-01 18:10 ET)
- [x] Approval 3, merge version `platform-2026-10-01.person-feed-1`: operator
  "approved", recorded by `rules approve` (2026-10-01 18:11 ET)
- [x] Approval 4, source version `sec.submissions.person-2026-10-01.first`:
  operator "approved", recorded by `rules approve`; `rules status` confirms
  both approvals and their words (2026-10-01 18:18 ET)
- [ ] `rules activate` (needs `RULES_MDM_ACTIVATION_DATABASE_URL`, a Clean MDM
  database). Not reached. After merge, `policy.yaml` has a new digest, so
  Company runs also need `rules activate --merge platform` before they run,
  as after the name rules (2026-09-29)
- [ ] Before switch-on: the operator confirms feed 1 may go live without
  relationship links, which feed 1 cannot build (ruling: "there has to be
  relationship along with mdm it can not be separated")
- [x] Adversarial fixture for `sec-person-candidate`: `hard-cases-checked.jsonl`,
  57 cases, 0 violations, in `pending-proofs.yaml` (2026-10-01 about 09:01 ET)
- [x] Pinned tests broken by adding a kind: fixed by PR #769 (05a), merged
  2026-10-01 09:27 ET
- [x] Skill gaps ticketed: `05c-data-onboarding-skill-gaps.md` (16 items,
  including the Mapping Document bugs and the identifier-approval gap)
  (2026-10-01 18:25 ET)
- [x] Three-axis `/code-review` (2026-10-01 18:25 ET); PR #770 opened
- [x] CI's first run failed three unit tests I had not run locally. Fixed with
  the operator's "yes" (code): `resolve_feed` picks the document that acquires
  the feed; Mapping Document words (05c item 10, part); the pinned document
  set. Reviewed on three axes. Unit 394, MDM 484, architecture 249 passed
  locally (2026-10-01 18:34 ET)
- [x] CI green; merged as #770 on the operator's "Merge" (2026-10-01 18:46 ET)

## Out of this PR

- A Person reader (production code that lands Person readings for a
  Bookkeeping run). The proving run reads the raw files with `normalize`, as
  a labelled test input.
- Feeds 2–5 (Forms 3/4/5 owners, 8-K 5.02, DEF 14A, ADV Schedule A/B):
  listed as next tickets only.
