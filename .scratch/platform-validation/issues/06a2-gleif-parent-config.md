# Switch on the GLEIF accounting parent (06a, part 2: configuration)

Type: task (configuration, two small code changes)
Status: done except switch-on (merged as #773; both versions approved on the local Rules Database)
Parent: `06-relationship-rules.md`; engine in #771 (06a)

## Operator rulings (2026-10-01)

- Design 1 and design 2, and "Yes" to the engine (#771, merged 20:32 ET).
- "Yes" to 06a part 2, including two small code changes:
  - the GLEIF reader rewrites a link's start source as it rewrites its end;
  - the Mapping Document shows the start key.
- 21:16 ET: "yes" to ticket 05b doing the database fixes after 06a2 merges:
  indexes (research note findings 1, 3, 4, then 2 after measuring) and
  reviews no longer copying the whole save's subjects and entities (the cause
  of try 1's 24 MB save). Note: `.scratch/platform-validation/research/05b-mdm-database-tuning.md`.

## What changes

- **`rules/sources/gleif/source.yaml`:** the relationships mapping gains
  `source_key: [start]` and `source_source: gleif.level1.v1`, so a GLEIF
  relationship record starts at its child's Level 1 record.
- **`rules/merge/kinds/company.yaml`:** `gleif.relationships.v1` joins
  `defaults.sources`. It maps no fields, so no field changes.
- **Code:**
  - `gleif_source.dataset_contract` rewrites `source_source` with
    `target_source`;
  - `mapdoc` shows a link's start key;
  - the skill's REFERENCE row learns `source_key`.
- **Pins:** the GLEIF relationships contract and Company's policy get a
  layer each, so the approved digests still peel back.

There is no separate "relationship rule" to switch on. The engine projects
every supported link whose two ends are accepted Companies. The gate is the
merge version and the GLEIF source version, each approved by the operator
on a test run. The relationship rules document (06, step 2) is designed
after this.

## Checklist

- [x] GoF consult on `gleif_source.dataset_contract` and `mapdoc` links (2026-10-01 22:13 ET, leave it). It ran after the code, as the review's GoF axis; CLAUDE.md asks for it before, and it was missed
- [x] Code: `source_source` rewrite; mapdoc start key; REFERENCE row (tests/mdm, unit; 2026-10-01 20:35 ET, about)
- [x] Configuration: GLEIF mapping, Company sources (`test_clean_company_source`; 2026-10-01 20:35 ET, about)
- [x] Pins: GLEIF relationships layer, Company policy layer; zero approved
  hashes changed (peeling gives 75bd2b67… and the approved GLEIF contract; 2026-10-01 20:35 ET, about)
- [x] Mapping Documents regenerated; `mapdoc check` exit 0 (2026-10-01 20:35 ET, about)
- [x] Test run: ticket 27's Companies plus their GLEIF Level 1 and relationship
  records on a throwaway PG16, twice. Count the parent links, those waiting
  and why, and conflicts (try 3, 2026-10-01 21:51–22:07 ET, on #772, saves of
  200; `.scratch/platform-validation/research/06a2-report.json`)
  - Company results equal ticket 27's: 6,414 Companies, 3,052 with CIK and
    LEI, no CIK or LEI on two Companies, 664 GLEIF records waiting for
    binding, 312 SEC records deferred for classification.
  - GLEIF relationship records with both ends in the cohort: 272. Read as
    links: 268; set aside 4 (`unsupported_relationship_type`).
  - Parent links: 86 direct (`IS_DIRECTLY_CONSOLIDATED_BY`), 110 ultimate
    (`IS_ULTIMATELY_CONSOLIDATED_BY`), and 86 calculated ultimate parents.
  - Waiting: 72 open `unresolved_endpoint` reviews, links whose other end is
    a GLEIF record not yet joined to a Company (among the 664). No parent
    conflicts, no cycles.
  - Second pass changed nothing (Companies, decisions, reviews, links).
  - Largest save 6.3 MB (SEC parts); GLEIF saves about 2.6 MB; link saves
    2.4 MB and 1.2 MB. Before #772 they were 19 MB and 24 MB.
  - Try 1 (20:42–21:02 ET) stopped: the first save of 200 links was 24 MB,
    over the 16 MiB cap in `write_batch`. Why: every review in a save carries
    the subjects and entities of the whole batch (`merge.py`, the review
    projection's `affected_subjects`/`affected_entities`), so size grows with
    reviews × batch. Try 2 saved links 25 at a time and started
    21:03 ET; try 3, on the fix, saves 200 again. The quadratic review size is a finding for 05b.
  - Try 2 (21:03–21:25 ET): the first pass finished. 3,755 GLEIF Level 1
    readings in 19 saves of 200, then 272 links in 11 saves of 25. Second
    pass: SEC parts changed nothing (0 records each). The first GLEIF save of
    the second pass was 19 MB and was refused. Why: the closure is transitive
    (`load_closure` loops until no key is added), so once links exist, 200
    GLEIF records pull in their linked companies and every reading of those;
    every review then copies that larger closure's subjects. Same root cause
    as try 1; it now hits a re-delivery of ordinary GLEIF records, which
    GLEIF's daily file does.
- [x] Unit, MDM and architecture suites, and the named integration files (rebased on #772, 2026-10-01 22:07–22:11 ET: MDM+unit 884, architecture 249, test_clean_mdm_postgres 46, identifier_binding 24, change_journal_source_evidence 30, relationship_identity 5, review_scope 3, company_one_place 6; `mapdoc check` exit 0)
- [x] Three-axis `/code-review` (2026-10-01 22:16 ET). GoF: leave it; copy the
  contract before rewriting it. Standards: the GLEIF reader tests `source_key`
  as the adapter and mapdoc do; a plainer test helper; ticket notes and times.
  Spec: no blocker; a mapdoc test for the start row. Fixed; affected files
  206 passed
- [x] PR #773; CI green (2026-10-01 22:18 ET); merged on the operator's "yes" (2026-10-01 22:19 ET)
- [x] Approvals: merge version, GLEIF source version (local Rules Database
  `rules-local-person-feed-1`; inputs `inputs-06a2.json`, 86 files, batch_hash
  6724ca69…623b; proofs in the cm27 proving folder)
  - Merge version `platform-2026-10-01.gleif-parents`, digest 4c9d1cee…26f8,
    evidence_hash 8a8802b2…24eb. Without its one change it is the approved
    Person feed 1 version (da4b5065…). Operator: "approve" (2026-10-01 22:21 ET).
  - GLEIF source version `gleif-2026-10-01.parent-links`, digest
    fecfcbf9…9347, evidence_hash f2aab418…f62b. Operator: "approve"
    (2026-10-01 22:21 ET).
- [ ] ~~Switch on (`rules activate`)~~ deferred to the switch-on step for
  Person, Company and GLEIF links: it needs a Clean MDM database, and
  recreating `edgartools-clean-mdm-pg16` is the operator's call
- [ ] Open for slice 6 step 2 (relationship rules document): the 72 links
  waiting for their other end are open reviews today; whether they belong in
  a quieter waiting state, like records deferred for classification
