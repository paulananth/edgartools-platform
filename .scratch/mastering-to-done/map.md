# Company, Person and Relationship mastering: what is left

## Destination

Company, Person and their relationships are switched on in a fresh local Clean MDM. They are fed through configured parsing, Bookkeeping and the Change Journal, with data quality checks and the Data Catalog current. Every open ticket's status matches git.

## Notes

- Operator, 2026-10-02: "what is still pending for mdm, config parsing, bookkeeping, change journal, dq, data catalog anything else for company, people and relationship need a compact to do".
- This map carries execution as well as decisions: a ticket is either a decision (grilling) or one build slice (task).
- **Standing rules:**
  - one branch and worktree per ticket;
  - the GoF consult before code, and the three-axis `/code-review` after it;
  - only the affected tests run locally, and CI runs everything;
  - merge only on the operator's word;
  - no SEC requests without the operator's permission;
  - only the operator approves or switches on rules.
- **Grilling tickets:** use the `grilling` and `domain-modeling` skills, one question at a time.
- **Starting state** (2026-10-02 10:30 ET, main `4e51a84f`):
  - **Approved:** Company (CIK and the two name rules), the GLEIF accounting parents and Person feed 1. All are approved on the local Rules Database `rules-local-person-feed-1`, and none is switched on.
  - **No local Clean MDM database:** the old pg16 store was deleted today, with a backup kept.
- **Enabled commands:**
  - `mdm`: migrate, prepare-clean-company, name-census, counts, check-connectivity;
  - `bookkeeping`: init, migrate, init-guard, prepare, runs, status, checks, leases, resume;
  - `change-journal`: init, migrate, status, events, verify, recover;
  - `rules`: init, migrate, load, unload, mapdoc, catalog, pending, save, status, export, record-proof, approve, activate, run.

## Sequence

Work in this order. A ticket starts when everything it is blocked by is resolved.

| # | Ticket | Blocked by |
|---|---|---|
| 01 | [Correct stale ticket statuses](issues/01-correct-stale-ticket-statuses.md) | resolved (#787) |
| 02 | [Relationship rules design](issues/02-relationship-rules-design.md) | resolved (#786) |
| 03 | [Data quality for Person and links](issues/03-data-quality-for-person-and-links.md) | resolved (#791) |
| 04 | [The command that runs mastering](issues/04-the-command-that-runs-mastering.md) | resolved (#788); the command is down from 20a until 20e |
| 05 | [Review findings 5 and 6](issues/05-review-findings-5-and-6.md) | resolved (#789) |
| 13 | [Waiting links wait quietly](issues/13-waiting-links-wait-quietly.md) | resolved (#793) |
| 08 | [Configured parsing: engine or per-source readers](issues/08-configured-parsing-engine.md) | resolved (#790) |
| 11 | [Data Catalog for Person and links](issues/11-data-catalog-for-person-and-links.md) | resolved (#792) |
| 14 | [The Person link engine](issues/14-person-link-engine.md) | 02 |
| 06 | [Switch on Company and the GLEIF parents](issues/06-switch-on-company-and-gleif-parents.md) | 02, 04, 05, 13 |
| 07 | [Cascade passes: label and switch on](issues/07-cascade-passes-switch-on.md) | 06 |
| 15 | [Rust engine core behind Python](issues/15-rust-engine-core-behind-python.md) | 08 |
| 16 | [GLEIF on the engine](issues/16-gleif-on-the-engine.md) | 15 |
| 17 | [SEC Company on the engine](issues/17-sec-company-on-the-engine.md) | absorbed into 20c |
| 09 | [Test, check and Preview for onboarding](issues/09-test-check-and-preview-for-onboarding.md) | 15 |
| 10 | [Forms 3/4/5 capture and reader](issues/10-forms-345-capture-and-reader.md) | 02, 09, 14, 15 |
| 18 | [Person and link quality rules](issues/18-person-and-link-quality-rules.md) | 03, 14 |
| 19 | [Restore the catalog and publish Person and links](issues/19-restore-the-catalog-and-publish-person.md) | 11, 18 |
| 20 | [Bookkeeping without legacy or custom code for Company and Person](issues/20-bookkeeping-without-legacy-or-custom-code.md) | none (slices 20a–20e) |
| 12 | [Switch on Person feed 1 with its links](issues/12-switch-on-person-with-its-links.md) | 03, 06, 10, 11, 18, 19, 20 |

## Decisions so far

- [Relationship rules design](issues/02-relationship-rules-design.md): GLEIF parents plus Forms 3/4/5 insider links (Person, Company, capacity; one record per filing); waiting links wait quietly; the other link kinds come later.
- [Data quality for Person and links](issues/03-data-quality-for-person-and-links.md): the proposed set of checks (operator: "Proposed set (Recommended)"); built in ticket 18.
- [The command that runs mastering](issues/04-the-command-that-runs-mastering.md): `edgar-warehouse rules run --target mdm`; no `bookkeeping run`.
- [Configured parsing](issues/08-configured-parsing-engine.md): build the engine first, a Rust core always called through Python; custom readers only as a last resort; built in tickets 15–17.
- [Data Catalog for Person and links](issues/11-data-catalog-for-person-and-links.md): the catalog and the Mapping Documents both before switch-on; built in ticket 19.

## Not yet specified

- Person feeds 3–5: 8-K item 5.02 officers, DEF 14A (blocked by the edgartools name defect), ADV Schedule A/B (CRD and OwnerID, not parsed yet).
- A full Person acquisition and preparation reader. Today the Person feed reads the submissions only through the fixture conversion.
- The Person timing run and save profile: the deferred evidence for the lookup indexes (05b).
- Silver outputs from the rules (rules skill 05: Delta and/or Lakebase).
- Hosted cut-over to Snowflake Postgres for MDM, once local switch-on holds.
- A Security kind (tickers belong on Security, not Company).
- Suspended identifiers: whether a suspended CIK or LEI defers a binding (company mastering 04, never decided).

## Out of scope
