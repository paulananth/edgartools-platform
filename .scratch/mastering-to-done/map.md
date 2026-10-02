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

## Decisions so far

## Not yet specified

- Person feeds 3–5: 8-K item 5.02 officers, DEF 14A (blocked by the edgartools name defect), ADV Schedule A/B (CRD and OwnerID, not parsed yet).
- A full Person acquisition and preparation reader. Today the Person feed reads the submissions only through the fixture conversion.
- The Person timing run and save profile: the deferred evidence for the lookup indexes (05b).
- Silver outputs from the rules (rules skill 05: Delta and/or Lakebase).
- Hosted cut-over to Snowflake Postgres for MDM, once local switch-on holds.
- A Security kind (tickers belong on Security, not Company).

## Out of scope
