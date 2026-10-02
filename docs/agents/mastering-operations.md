# Mastering operations

## Executable paths

Read the CLI parser and capability registry before running an older command.
The CLI entry is `edgar_warehouse/cli.py`; configured execution is
`edgar_warehouse/bookkeeping/clean/`; mastering is
`edgar_warehouse/mdm/clean/`; source and domain declarations are `rules/`.

| Domain | Input and rules | Boundary |
| --- | --- | --- |
| Company | SEC Company submissions landing and GLEIF Level 1; `rules/merge/kinds/company.yaml` | Filing history forms are evidence within the Company document. They are not separate form-based mastering inputs. |
| Person | Raw SEC individual-filer submissions; `sec.submissions.person.v1` and `rules/merge/kinds/person.yaml` | The approved feed covers individual filers. Forms 3/4/5 owners, 8-K officers, DEF 14A and ADV people require their own onboarding. |
| Relationships | GLEIF relationship records with explicit child/parent subjects, plus the typed projection engine | A relationship needs accepted canonical endpoints, compatible kinds and valid periods. Missing or conflicting endpoints produce reviews. |

`mdm` exposes migrate, check-connectivity, counts, name-census and
prepare-clean-company. Mastering work is submitted through configured
Bookkeeping capabilities (`mdm.ingest`, `mdm.merge`, `mdm.publish`).
Do not revive retired `mdm mastering`, warehouse batch commands, or parsers
by copying a historical example.

Person feed 1 has an approved Dataset Contract and matching/classification
rules; a full Person acquisition/preparation reader is still separate work.
The local cohort reconstructs the adapter's raw field names from the pinned
fixture. It does not implement that reader or certify all Person populations.

## Fresh local qualification

Prepare Colima/Docker, the PostgreSQL image and locked dependencies:

```bash
colima start
docker pull postgres:16-alpine
uv sync --frozen --extra s3 --extra mdm
uv run python scripts/ops/qualify_local_mastering.py \
  --output-root /tmp/mastering-qualification-<unique-run>
```

The output directory must be new. The command checks Docker and the image,
then runs fresh mastering acceptance, all four pytest folders and shell syntax
checks, retaining logs and JUnit results. It is the long, whole-suite run: for
everyday work, run the affected tests locally and let CI run everything
(operator, 2026-09-29); run this only when it is the evidence asked for. Each suite has a five-minute budget. PostgreSQL skips,
missing test cases, a timeout or a missing prerequisite leave `qualified`
false. Fixtures create disposable PostgreSQL 16 stores and restricted runtime
roles and remove their own stores on completion. Hosted credentials are unused.

The new bounded cohort uses the repository's unchanged Company and Person
rules. Two GLEIF Level 1 records and one synthetic accounting-parent record go
through the real GLEIF reader; a steward binds each GLEIF record to its SEC
Company, and the link must resolve to those canonical Company IDs. Physical
local publication read-back verifies immutable envelopes. The parent record
establishes no real GLEIF fact. No Person link type is approved yet (platform
validation 06, step 2), so the cohort has no Person link.
Separate existing tests cover GLEIF parent periods, real Journal delivery,
Rules/Bookkeeping authority, acquisition pagination and failure recovery.

Shell syntax remains part of CI: syntax-check tracked shell scripts in
`infra/scripts/` and `scripts/`. A local evidence report is not a hosted
deployment, a production rule approval, or a claim that a full cohort ran.

## Database inventory and cleanup

The active stores are separate logical responsibilities:

| Store | Active schema and owner |
| --- | --- |
| MDM | `mdm`: identities, readings, decisions, Stage/Master views and publication intents |
| Bookkeeping | `bookkeeping`: work, leases, checkpoints and journal outbox |
| Rules | `rules`: mapping/policy versions, proof and approval |
| Change Journal | `journal`: immutable shared history and source/publication evidence |

`bookkeeping_guard` is destination transaction authority, not a spare
database. Per-kind Stage/Master views are not duplicate stores. Test template
databases are active while tests use them. A database named `mdm`, `silver`,
`bookkeeping`, or `change_ledger` is not proved unused by its name.

Before deleting a pre-existing local database, inspect the exact container and
database, schemas, current connections, configured callers, retention purpose
and recoverability. Record exact no-use evidence and the operator-authorized
target in the ticket. Delete only those targets and verify the remaining
active stores. Never prune all Docker volumes or remove an entire Colima VM
as a substitute for that inventory.

If Docker access is unavailable, report database inventory, qualification and
deletion as incomplete. Preserve existing evidence captures and rollback data.

## Agent memory

Keep dated evidence in tickets instead of copying changing runtime state into
CLAUDE.md or AGENTS.md. Consolidating those two guides is its own ticket
(operator, 2026-10-02).
Verify memory claims about commands, migrations and deployments against current
code. Preserve operator decisions and historical evidence when superseding
stale implementation guidance.

Codex memory changes are submitted as one small update note under
`~/.codex/memories/extensions/ad_hoc/notes/`, only on the operator's explicit
request. Do not rewrite the generated memory registry. Claude memory is outside
the repository; changes need filesystem access to that location and should
retain the operator's standing feedback.
