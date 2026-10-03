# Change Journal independence: findings and implementation

Date: 2026-10-02. Owner: Codex. Base: main `3934f967`.
Status: implemented; local qualification recorded below. No deployment,
package publication, stored-history migration or Claude assignment.

## Finding

The previous implementation was coupled. `change_journal` contained provider
capture/completeness, Rules authority, source inventories, MDM publication and
producer workflow orchestration. Its generic store/migrations imported pure
helpers from Bookkeeping's configuration module. Its CLI constructed
Bookkeeping and MDM clients for recovery. Journal qualification through the
old skill could therefore execute a producer workflow.

The journal's existing append/get/list/status/verify interface was already
sufficient. The GoF review of the current source and #738/#755/#757/#767 history
supported correcting ownership and composition without a new class hierarchy.

## Implementation

| Previous placement | Owning implementation |
| --- | --- |
| `change_journal.capture` | `acquisition.capture` |
| `change_journal.decisions` | `acquisition.decisions` |
| `change_journal.authority` | `rules.acquisition_authority` |
| `change_journal.source_evidence` | `application.source_evidence` |
| `change_journal.publication` | `mdm.clean.journal_delivery` |
| `change_journal.skill` | `application.journal_evidence` |
| Recovery handlers in the journal CLI | `application.journal_recovery` |

All executable imports and test patch targets were updated. The old module
paths and journal skill orchestration script have no compatibility wrappers.
The workflow helper is now `edgar-warehouse plan workflow`.
It remains application composition, not proof of Bookkeeping independence.

Canonical JSON, hashing, reference validation and `Blocked` were extracted
unchanged to `control_contract.py`. Bookkeeping config reexports the exact same
objects for its existing consumers. AST comparison verified all four extracted
definitions and all six moved integrations' non-import code were unchanged.
Journal migration SQL, envelope version, keys, canonical hashes, receipts and
readback semantics are unchanged.

The journal core has four Python files plus its SQL migration. Its imports are
limited to itself, the pure shared module, the standard library and SQLAlchemy.
It constructs no owner engines and invokes no business callbacks. Producer,
source and feed labels remain opaque metadata; an unseen producer is admitted
without a domain registry or configuration change.

## Independent installation

`packages/change-journal/pyproject.toml` builds `edgartools-change-journal` from
the canonical repository files. The wheel contains only the seven required
warehouse source/SQL files and distribution metadata. Its direct dependencies
are SQLAlchemy 2.0 and psycopg2-binary. It provides `edgar-change-journal`
init/migrate/status/events/verify. The full warehouse CLI composes the existing
Bookkeeping/MDM recovery commands in the application layer.

Use a dedicated virtual environment: the journal and warehouse distributions
share a namespace and must not be co-installed. Build the wheel from the
repository; a portable source distribution and deployed container are outside
this qualification. Installation commands and responsibilities are in
[the skill dependency contract](../../skills/change-journal/INDEPENDENCE.md).

The first clean installation caught an actual driver mismatch: unbounded
SQLAlchemy resolved to 2.1.2, while the wheel declares psycopg2. SQLAlchemy 2.1
changed plain `postgresql://` URLs to default to psycopg 3. The wheel now bounds
SQLAlchemy to `>=2.0.0,<2.1`, retaining the repository lock's driver behavior.
This was verified against [SQLAlchemy's migration documentation](https://docs.sqlalchemy.org/en/21/changelog/migration_21.html#default-postgresql-driver-changed-to-psycopg-psycopg-3).

## Verification

- Architecture tests inspect core and shared-module imports, start a physical
  copy without domain modules, and deliberately reintroduce a Bookkeeping
  import to prove that the guard rejects it. CLI handler ownership is checked.
- The independent wheel test installs into a clean environment, checks exact
  contents and absence of edgartools/PyArrow/lxml/ijson/boto3, and uses isolated
  interpreter mode plus the import guard. It initializes an empty disposable
  PostgreSQL 16 journal, then exercises migration retry, append, identical retry,
  conflicting key rejection, listing and receipt readback. Runtime is
  `ledger_runtime`, a non-superuser with no direct journal table access.
- Existing producer tests retain separate authorization, outage/recovery,
  lost-acknowledgement, fencing/CAS, rollback, Company pagination, MDM publication
  and Rules accounting checks. Existing test changes only update imports and
  patch paths; no assertions or cases were deleted. Five cases were added.
- Skill frontmatter, references, CLI ownership and installed discovery were
  checked. The dangling shared skill link was repaired; its existing mirror was
  preserved. Both resolve to this owned worktree.

### Recorded local runs

| Run | Result | Elapsed |
| --- | --- | --- |
| Initial architecture and control contract selection | 56 passed | 17.64 s |
| Affected PostgreSQL suites | 113 passed, no skips | 625.21 s |
| Unit + architecture + MDM | 1,127 passed; 9 failed due to missing local openpyxl | 458.92 s |
| Mapping Document rerun with locked openpyxl 3.1.5 / et-xmlfile 2.0.0 in a temporary dependency directory | All 15 passed, resolving those 9 failures | 138.25 s |
| Duplicate local integration suite, interrupted after GitHub full gate passed | 180 passed, 1 xfailed, earlier fixed wheel driver failure; not a complete local gate | 1,045.87 s |
| Corrected independent wheel acceptance | 1 passed, no skips | 114.22 s |
| Final architecture import/CLI checks | 4 passed | 10.70 s |

The three broad suites contain 395 unit, 251 architecture and 490 MDM cases
(1,136 distinct cases). Temporary dependencies avoided modifying the shared
checkout's environment. Shell syntax checks passed for all current CI script
roots. The [published PR](https://github.com/paulananth/edgartools-platform/pull/794)
passed the [complete GitHub gate](https://github.com/paulananth/edgartools-platform/actions/runs/37034880553)
on implementation commit `49bcf9b6`: 395 unit, 251 architecture, 491 MDM and
295 integration cases passed, with one retained expected failure and no skips.
The integration test command took 142.96 s; its entire job took 169 s. Run
creation to gate completion took 178 s, including 2 s before the first job
started. Main had advanced to `8aecca6d`; the merge was tested without any
owned-file overlap. No CI layout/runtime improvement is claimed by this task.

The duplicate local integration run was interrupted after this full gate passed
and a separate storage check showed the Mac nearly full. Its only failure was
the pre-repair wheel installed earlier in that process. The corrected wheel
passed both the dedicated local run and the full GitHub integration suite.
This final documentation update has its own automatic CI run; the successful
implementation gate and tested commit are explicitly recorded above.

## Limits

This qualifies the journal core and independent wheel. Application composition
still uses Bookkeeping and MDM, and Bookkeeping's own loader coupling remains
separate implementation work; PR #785 records its design/skill requirements.

Journal verification certifies envelope shape, canonical hash and exact durable
storage. It does not fetch evidence URLs, certify business contents, approve
Rules or authenticate individual producer labels. Owners retain those duties
and their transaction-local outboxes. Journal and producer commits are separate;
original keys/envelopes reconcile delivery after lost acknowledgement.

No live AWS/Snowflake/PostgreSQL deployment or stored history changed. Old roots
and retained audit stores remain separate. No runtime fallback or business
schema was added to the journal.
