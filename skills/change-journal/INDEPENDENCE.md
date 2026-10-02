# Journal dependency boundary

The core is `edgar_warehouse/change_journal`: store, database migrations,
envelope/receipt exports and the standalone journal CLI. Its only warehouse
dependency is `control_contract.py`, which contains pure canonical JSON, hash,
reference validation and the shared control exception. No runtime owner is
imported by those primitives.

## Producer ownership

| Responsibility | Implementation outside the journal |
| --- | --- |
| Provider fetching and format completeness | an acquisition worker (mastering to-do 20c; the in-process `acquisition` callbacks were deleted in 20a) |
| Frozen Rules acquisition/registration authority | `rules.acquisition_authority` |
| Source revisions and producer inventories | a source-evidence worker (mastering to-do 20c; deleted from `application` in 20a) |
| MDM outbox delivery and committed-effect checks | `mdm.clean.journal_delivery` |
| Producer workflow planning (validation and execution return with the workers, 20c) | `application.journal_evidence` |
| Composition of owner recovery commands | `application.journal_recovery` |

These owners call append/get/verify. The journal never calls them back or
constructs their engines. Business verifiers remain external. Moving a loader
to another filename while retaining a journal import would violate the boundary.

## Proof of independence

`tests/architecture/test_change_journal_independence.py` checks static imports,
starts a copy containing only journal code and pure contracts, blocks other
warehouse modules and domain libraries, admits an unseen producer, and proves
that a deliberately injected Bookkeeping import fails. Root CLI recovery
handler ownership is also checked.

`tests/integration/test_change_journal_independence_postgres.py` builds and
installs the independent wheel in a clean virtual environment. It checks the
exact packaged files and absence of domain libraries, then runs actual
init/migrate, append/retry/conflict, event listing and receipt verification
against PostgreSQL 16. Isolated interpreter mode prevents repository imports;
the import guard also rejects domain dependencies. The runtime role has no
direct table access. Missing prerequisites fail.

Require both static and runtime isolation after changing the core; an import
search alone misses transitive/dynamic dependencies. A full warehouse install
may still include other libraries for other commands; that is not the core's
runtime dependency closure.

## Independent installation

`packages/change-journal/pyproject.toml` builds a wheel from the canonical core
files and SQL migration. Its direct dependencies are SQLAlchemy and
psycopg2-binary, with their required transitive dependencies. Build the wheel
from this repository and install it in a dedicated environment:

```bash
uv build --wheel packages/change-journal --out-dir <wheel-dir>
uv venv <journal-venv>
uv pip install --python <journal-venv>/bin/python <wheel-path>
<journal-venv>/bin/edgar-change-journal --help
```

The independent and full warehouse wheels share the `edgar_warehouse`
namespace: do not install both distributions in the same environment. Only
the wheel built from the repository is supported here; no standalone source
distribution, container rollout or PyPI publication is qualified by this task.

## Limits of receipt verification

Journal verification checks envelope shape, canonical hash and exact durable
readback under restricted database functions. It does not open evidence URIs,
validate business payloads, approve Rules, validate source scope or certify
producer work completion. Producers retain those obligations and their
transaction-local outboxes. A producer label is metadata, not a separate
producer-authentication mechanism.

The journal transaction is separate from destination/control commits. Retry
the same original key/envelope after lost acknowledgement; conflicting content
blocks. Preserve required pre-request authorization delivery and current lease
checks in the acquisition owner. Retain old stacks for old roots/backlogs.
Do not add domain schemas, mutable work state, fallback connections or legacy
replay to the journal to satisfy an integration request.
