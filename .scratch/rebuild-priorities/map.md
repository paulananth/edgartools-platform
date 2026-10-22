# Rebuild priorities

Labels: wayfinder:map. Charted 2026-10-13 ET, from the 70 tickets left open after the stale-ticket cleanup (mastering-to-done ticket 25).

## Destination

The rebuild carries the captured data end to end, and proves it. Every captured feed has a reader and a Dataset Contract. Company, Person, the ownership links, Security and the financials are mastered, written to silver, and readable through `edgar-warehouse context`. The operator accepts both the recreation proof (ticket 32) and the financials cohort proof (ticket 48).

## Notes

- **Ticket number = priority.** Ticket 01 is the most urgent. The frontier is the lowest-numbered ticket that is open, not blocked and not claimed. The order rule (operator, 2026-10-13, "Agreed"):
  1. **Tickets 01–08, in flight:** work already started, or blocked only on the operator's answer.
  2. **Tickets 09–32, the recreation proof:** what the proof needs, in dependency order.
  3. **Tickets 33–62, product value:** the financials first, then the promotion criteria, the agent decision inputs and the dashboards.
  4. **Tickets 63–67, housekeeping:** needs no SEC requests.
  5. **Tickets 68–71, gated:** each needs SEC requests or AWS. They wait for the operator's permission.
- **Execution is in scope.** This map carries build tickets as well as decisions, like the profiling map does. Each build ticket gets:
  - its own branch, cut fresh off origin/main, in its own worktree;
  - a GoF consult before code;
  - a three-axis `/code-review` (Standards, Spec and GoF);
  - the overlap guard before every commit and push;
  - CI green;
  - a merge only on the operator's word.
- **Moved tickets keep their history.** Each ticket was moved from its own effort, and the old path holds a one-line "moved" note. The old effort's map keeps its decisions. In a Blocked by line, a list of numbers uses this map's numbers, or names the old effort ("mastering-to-done 03") when that ticket was not moved. Free text keeps the old effort's numbers.
- **Standing rules:**
  - no sec.gov request and no prod change without the operator's permission;
  - the repo is public, so fixtures are invented and outputs hold counts only;
  - every lookup uses an index;
  - names are the source's own;
  - each checklist part is ticked with its evidence and an ET time.
- **Answered (operator, 2026-10-13 20:30 ET, "Create its own (Recommended)"):** the ownership feed masters each reporting owner (Person or Company, by CIK) together with its insider link; it does not wait for the submissions feed.

- **Answered (operator, 2026-10-14 08:19 ET):** Form ADV's custodian links come back once the Merge Stage has no limit (ticket 75, "Yes, a new ticket"); the GLEIF cascade and Form ADV matching rules, declared but not switched on, are measured and then switched on or deleted (ticket 76, "Track them on the map"). For the ownership feed, a ten-percent owner is linked `BENEFICIAL_OWNER_OF` ("BENEFICIAL_OWNER_OF (Recommended)"), and a random 50 of the 198 owners with no submissions document are checked before its switch-on ("Check a sample first (Recommended)"); both are recorded in ticket 01.

## Route to completion

Reviewed 2026-10-21 20:14 ET, over all 127 tickets. Operator, asked what "complete the project" means: "Two proofs, local (Recommended)". The destination above stands: done when the operator accepts the recreation proof ([32](issues/32-profiling-08-recreation-proof.md)) and the financials cohort proof ([48](issues/48-company-financials-16-cohort-proof.md)) on local stores. This order replaces "ticket number = priority" for what is left:

1. **Close what is finished** (docs only, one session). The work is merged; only "PR / merge / learning" ticks or deferred parts stay open: 02, 03, 04, 06, 07, 10, 11, 13, 16, 17, 19, 22, 23, 66, 74, 76, 86, 88, 89, 100, 101, 105, 111, 112, 113, 115, 116, 117, 118, 123. Tickets 50–62 were closed by the ruling of 2026-10-18 ("Close all, re-raise later"); mark their files closed in this step too.
2. **Switch on what is proved** (each on the operator's words): [120](issues/120-switch-on-securities.md) Securities, then OpenFIGI, in `company-on` (about 3 h, then about 7 h of merge); [114](issues/114-onboard-company.md) Company; [80](issues/80-onboard-openfigi.md) OpenFIGI's source activation; [09](issues/09-mastering-to-done-07-cascade-passes-switch-on.md) the cascade passes (about 1½ h of the operator's labels, 344 pairs).
3. **Close the mastering gaps**, so every captured feed is read and mastered: [01](issues/01-profiling-07-readers-per-feed.md) Form ADV's custodian links; [24](issues/24-security-mastering-04-form-4-attaches-by-class.md) a Form 4 attaches by share class; [25](issues/25-security-mastering-05-a-person-holds-and-does-not-issue.md) a Person holds and does not issue; [79](issues/79-onboard-funds-and-securities-with-the-skills.md) 13F Securities and funds' `HOLDS`; [99](issues/99-an-identifier-rule-creates-after-the-name-rules.md) an identifier rule creates after the name rules.
4. **Build the financials to their cohort proof**: [35](issues/35-company-financials-03-time-model-as-reported-or-restated.md) and 37–47 in order, then [48](issues/48-company-financials-16-cohort-proof.md).
5. **Ready and run the recreation proof**: [14](issues/14-rules-skill-15-test-rules-locally.md) rules tested locally at full size, [20](issues/20-mastering-to-done-19-restore-the-catalog-and-publish-person.md) the catalog, [21](issues/21-clean-mdm-06-version-consumer-contracts.md) consumer contracts, [18](issues/18-profiling-05-agent-context-views-and-command.md) the context views, then [32](issues/32-profiling-08-recreation-proof.md).

Steps 3 and 4 can run side by side; step 5's proof runs last, on everything switched on.

## Decisions so far

- [Which measures analysts use, and the reported concepts behind each](issues/33-company-financials-01-which-measures-and-concepts.md): 19 line items by usage, concepts chosen per period, years keyed on period end
- [Capture permission and route for company facts](issues/34-company-financials-02-capture-permission.md): one bounded capture now, local only (operator, "a")
- [Capture the cohort's company facts](issues/36-company-financials-04-capture-the-cohorts-company-facts.md): 329 of 500 Companies have facts; 5.1 million facts in long form
- [MDM is just MDM: the words](../mastering-to-done/issues/26-mdm-is-just-mdm.md): "Clean MDM" is "MDM" in every living word (#956); the code names are ticket 73
- [Switch on Company and the GLEIF parents](issues/02-mastering-to-done-06-switch-on-company-and-gleif-parents.md): merge version approved and active locally; source activation moved to Bookkeeping on AWS
- [Bookkeeping without legacy or custom code](issues/03-mastering-to-done-20-bookkeeping-without-legacy-or-custom-code.md): every step a worker and verifier; the capture worker is #933; the live SEC run waits for AWS
- [Rust engine core behind Python](issues/04-mastering-to-done-15-rust-engine-core-behind-python.md): #799; streaming and multi-input steps are tickets 16 and 17
- [Self-sustaining data skill](issues/05-mastering-to-done-21-self-sustaining-data-skill.md): Company, GLEIF and Person read on the engine, old readers deleted, G3 passed again
- [Relationship rules](issues/06-platform-validation-06-relationship-rules.md): GLEIF parents and insider links switched on; Person feed 1 is ticket 11
- [Match proposal snapshot scaling](issues/07-platform-validation-05b-match-proposal-snapshot-scaling.md): the snapshot is gone; batch times flat over the full Person feed
- [Proving Run on a pinned cohort](issues/08-company-mastering-05-run-a-proving-run-on-a-pinned-cohort.md): whole population proved (6,414 Companies, 3,052 GLEIF bindings)
- [Person and link quality rules](issues/10-mastering-to-done-18-person-and-link-quality-rules.md): name-has-letter and link checks set records aside, never block (#967); each run reports its checks (#968); row-count change moved to ticket 71
- [Switch on Person feed 1 with its links](issues/11-mastering-to-done-12-switch-on-person-with-its-links.md): both feeds proved together, 31,326 people, 0 CIK conflicts; source activation moved to ticket 71
- [Check a step without redoing it](issues/72-check-a-step-without-redoing-it.md): a check confirms inputs, contract and output shape, and redoes the first unit and a 5% sample (#958)
- [The Merge Stage has no limit](issues/74-merge-stage-has-no-limit.md): no size refusal anywhere; how the input is cut stays (#960)
- [The Merge Stage merges record by record](issues/77-merge-one-record-at-a-time.md): a batch reads only the masters it touches and their links; proposal and batch in one transaction; the outbox reads a batch once (#963)
- [06 Silver writer](issues/17-profiling-06-silver-writer.md): a PG16 `silver` schema through one sink (#879); unchanged by the final source-extract and capture design
- [CSV and TSV are read the same](issues/86-tsv-reads-as-csv.md): one reader for both (#986, #989)
- [A reading looks up a value in a large set](issues/91-a-reading-looks-up-a-value-in-a-large-set.md): pair sets read by `member_value` (#993)
- [Capture posts a request with a key](issues/92-capture-posts-a-request-with-a-key.md): the OpenFIGI mapping capture (#994)
- [Skills hold every learning](issues/78-skills-hold-every-learning.md): `mdm-engineering`, data rules in the data skills, how to work in this repo in `AGENTS.md` and `CLAUDE.md` (#972, #985)
- [CLAUDE.md names deleted code](issues/85-claude-md-names-deleted-code.md): CLAUDE.md and AGENTS.md name only paths that exist, held by a test (#1006)
- [Profiling measures how identifiers pair](issues/90-profiling-measures-how-identifiers-pair.md): `pairs` in the findings says whether a second identifier joins one to one (#1008)
- [The identifier index keeps no pending list](issues/96-identifier-index-without-pending-list.md): migration 021; a Merge Stage batch 4.4 s to 2.5 s (#1007)
- [An init mode: the mapping document first, then the rules](issues/15-rules-skill-11-init-mode-mapping-document-and-catalog.md): the init mode, Mapping Documents and catalog publishing (#743)
- [Identifier types are configuration](issues/81-identifier-types-are-configuration.md): identifier types are configuration files, not code (#975)
- [A reduction reads several source extracts](issues/82-a-reduction-reads-several-readings.md): a reduction reads several readings (#978)
- [No output caps: large outputs are written in pieces](issues/83-no-output-caps.md): no output caps; large outputs are written in pieces (#981)
- [Profiling names the data quality rules, the RDM code sets and every silver field, and the catalog shows them](issues/87-profiling-names-quality-rdm-silver-in-the-catalog.md): profiling names quality, RDM and silver in the catalog (#987)
- [Simplify the tests, make them fast, delete old ones](issues/88-simplify-and-speed-up-the-tests.md): old and retired-code oracles deleted; every test states its own answer (#988); fixture sharing moved to 98
- [The engine tells whether two lists share a value](issues/93-two-lists-overlap.md): `overlap`: two lists share a value (#995)
- [The engine builds one text from parts](issues/94-text-from-parts.md): `concat`: text from parts
- [The engine takes a field of each object in a list](issues/95-a-field-of-each-object-as-a-list.md): `pluck`: a field of each object as a list

- [Point ISSUED_BY at a mastered Company](issues/22-security-mastering-02-issued-by-a-mastered-company.md): by issuer LEI; the issuer rule joins or waits, never creates; 0 duplicates, 41,360 links would resolve (#1022)
- [An N-PORT link starts at its quarter's data set](issues/100-an-nport-link-starts-at-its-quarter.md): the quarter dates each publication; the link starts there, observed (#1022)
- [A second N-PORT quarter is a new revision](issues/101-a-second-nport-quarter-is-a-new-revision.md): a quarter is a later revision with its own time; a link keeps its first observed start (#1023, #1026)
- [An ETF share is issued by its umbrella trust](issues/23-security-mastering-03-etf-share-issued-by-the-trust.md): each filed LEI counts as its GLEIF umbrella's; 540 more Securities linked, 1,967 moved from a fund series to its trust (#1038)
- [ISIN-only Securities link to their issuer](issues/102-isin-only-securities-link-to-their-issuer.md): by the one issuer LEI an ISIN's holdings state; 25,173 links, equal to a direct count (#1025)
- [Integration tests share their containers and fixtures](issues/98-integration-tests-share-containers-and-fixtures.md): one PostgreSQL 16 per session for the MDM store's tests; CI integration 310 s to 217 s (#1027)

- [A large CSV or TSV is read in pieces](issues/89-a-large-csv-or-tsv-is-read-in-pieces.md): a CSV or TSV larger than memory is read in pieces (#990)
- [09 Profiler gap: objects keyed by data are read as columns](issues/41-company-financials-09-profiler-reads-object-keys-as-columns.md): the profiler reads an object keyed by data as rows, not columns (#1016)
- [A run keeps the mappings it started with](issues/103-a-run-keeps-the-mappings-it-started-with.md): a run keeps the mappings it started with (#1037)
- [Stream a bare JSON array](issues/104-stream-a-bare-json-array.md): a bare top-level JSON array streams one record per element, with its position (#1044)
- [Silver rows are checked when they land](issues/105-silver-rows-are-checked-when-they-land.md): a silver spec declares identifier, in-set and one-value checks; a failing row lands flagged in `quality`, an `exception` check keeps it out (#1055)
- [One test helper runs the source chain](issues/106-one-test-helper-runs-the-source-chain.md): `tests/support/source_chain.py` reads, combines and prepares through each worker's verifier (#1054)
- [FIGI's check-digit family](issues/107-figi-check-digit-family.md): "luhn over letter values from the left"; FIGI version 2 checks it; 0 failures over 1,618,040 captured FIGIs (#1069)
- [One definition of the manifest task](issues/66-duckdb-retirement-cutover-23-consolidate-snowflake-run-manifest-task-definitions.md): Terraform owns `SNOWFLAKE_RUN_MANIFEST_TASK`; the script and bootstrap copies deleted, held by a test (#1076); the duplicated procedures are ticket 109
- [dbt and installs run through uv](issues/64-uv-migration-03-audit-dbt-invocation-sites.md): the runbook's dbt commands (#1078) and the dashboard and runbook installs ([65](issues/65-uv-migration-04-fix-examples-dashboard-pip-install-drift.md), #1079)
- [N-PORT's entity model](issues/30-nport-fund-holdings-07-entity-model-for-fund-complex.md): registrant a Company by CIK, series a Fund by series id and LEI, the instrument a Security by CUSIP or ISIN; questions 26-29 answered or moved to ticket 79's HOLDS part and ticket 71
- [Profiling ranks several sources](issues/110-profiling-ranks-several-sources.md): `rank_sources.py` measures coverage, one-value rate and pairwise agreement per field and writes the order in the kind file's shape (#1080)
- [Which filed words a Security keeps](issues/84-security-filed-words.md): OpenFIGI names a Security first, then N-PORT, then 13F; the title keeps the filed words; 3,688 of 3,927 cohort Securities take OpenFIGI's name (#1085)
- [rules test first](issues/12-mastering-to-done-09-test-check-and-preview-for-onboarding.md): the other onboarding commands fold into `rules test` (ticket 14); `rules profile` dropped

## Not yet specified

- **Where gold stands in the rebuild.** Answered (operator, 2026-10-18 12:25 ET, "Close all, re-raise later (Recommended)"): tickets 49–62 are closed as written for the retired gold layer; product value is re-raised against silver and the context views.
- **Hosting the rebuild.** Hosted Snowflake Postgres (ticket 68) and the AWS worker runtime (ticket 71) need the operator's destinations. The order of hosting and the recreation proof is not yet set.
- **Ownership contract follow-ups.** The ownership contract names its effective time but maps no `effective_at`, so its records state no time and the run checks report none; an issuer CIK that is malformed names no Company, so its link waits forever (none in the local copies). Each is a contract change that moves record ids.

## Out of scope

- The retired pipeline: the daily, bootstrap and load-history commands, their state machines, the DuckDB silver store and the old MDM runs. 77 tickets about them were deleted on 2026-10-13 (mastering-to-done ticket 25), and git history keeps them.
- **Past the two local proofs (review of 2026-10-21; operator: "Two proofs, local (Recommended)").** A later effort, not this map:
  - hosting: [68](issues/68-clean-mdm-07-qualify-and-cut-over.md) hosted Snowflake Postgres, [71](issues/71-mastering-to-done-24-worker-runtime-on-aws.md) the worker runtime on AWS;
  - SEC backfills: [69](issues/69-release-readiness-90-backfill-apple-494-missing-bronze-objects.md), [70](issues/70-release-readiness-103-backfill-mega-cap-missing-bronze-objects.md); [67](issues/67-mdm-enrichment-program-09-defer-existing-sec-bronze-migration.md) deferred;
  - one code for every engine: [119](issues/119-one-code-every-engine.md) (Codex, parked);
  - Security quality and speed: [121](issues/121-another-runs-reading-over-time.md), [122](issues/122-securities-run-time.md), [124](issues/124-profile-fund-share-classes.md), [125](issues/125-securities-and-funds-uniquely-identifiable.md), [126](issues/126-openfigi-for-13f-only-securities.md), [127](issues/127-folded-holdings-earliest-filing.md);
  - text from HTML, PDF and free text: [31](issues/31-profiling-07c-unstructured-extraction.md) (no captured feed needs it);
  - housekeeping: [63](issues/63-agent-guides-01-consolidate-claude-and-agents-md.md), [73](issues/73-mdm-is-just-mdm-code.md), [109](issues/109-one-definition-of-the-manifest-procedures.md).
