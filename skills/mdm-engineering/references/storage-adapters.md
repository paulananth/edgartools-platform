# Storage adapter contract and execution

Use this reference for PostgreSQL, MySQL or SQL Server Express selection,
missing storage support and the GoF review of that boundary. The executable
adapter and its SQL/model helpers live in this skill's `scripts/` directory.
They depend on SQLAlchemy and database drivers, not application modules.
The caller supplies prepared objects, evidence, frozen pins and publication
bytes from shared merge computation. Types and keys are opaque data; adding
a domain changes no adapter code or tables.

## Execute the skill resource

Resolve `SKILL_DIR` to this skill's directory. Discover the interface with:

```bash
uv run "$SKILL_DIR/scripts/database_adapter.py" --help
```

Select `--engine postgresql`, `--engine mysql` or `--engine mssql` and pass
`--connection-env` naming a private environment variable. The helper checks
that the URL's dialect matches. Use one consistent `--prefix` for its owned
objects; existing application schemas are not adopted or changed.

| Command | Connection and completion evidence |
|---|---|
| `provision --runtime-role <role> --password-env <variable>` | Owner login; provision a separate test runtime principal from the private variable, authenticate it and preserve an existing password. SQL Server needs a same-named login and database user. MySQL's `--runtime-host` defaults to `%`; choose the environment's intended host. This step alone grants no storage rights. |
| `migrate --runtime-role <role>` | Owner login; install the compiled logical model and atomic capabilities. Read back migration checksum, columns, keys, indexes, procedure bodies/security and restricted grants. A pending or incompatible migration refuses writes; rerunning the same build preserves populated state. |
| `status` | Runtime login; report the committed generation without row values or credentials. |
| `apply --input <private-json-file> --owner <worker>` | Runtime login; claim the scope and persist the prepared batch through the atomic destination capability. Report generation, checkpoint, duplicate and changed counts/flags. |

The standalone script carries uv dependency metadata; adjacent helpers ship
with it. The tested targets are PostgreSQL 16, MySQL 8 (8.0.21 or later), and
SQL Server 2022, including Express. SQLAlchemy's tested compiler version is
pinned so a dependency upgrade cannot silently alter the migration checksum.

`apply` requires `batch`, `run`, `scope`, nonempty `pins` and `assessment`,
`expected_generation` captured before preparation, `expected_checkpoint`,
advancing `checkpoint`, `objects`, `consumers` and
`payload` (or `payload_json`). Each object has opaque `type`, `id`, `body`
(or `body_json`) and `expected_version`. Optional `evidence` uses the same
opaque identity/body fields and is immutable. For a body or payload already
serialized by the shared engine, use the `*_json` field with its exact JSON
text. The adapter stores its original UTF-8 bytes and hash without numeric
or Unicode reserialization. Use frozen pins and assessment evidence from
the real owning workflow; fixture inputs remain qualification only.

For programmatic callers, use `PreparedBatch`, `Effect` and `Adapter` from
the script. `claim` returns a server-time scope lease and monotonic fence;
`apply` rechecks the lease, expected versions, generation, checkpoint and
frozen run pins at the destination. The same immutable batch intent can
recover a lost acknowledgement under a newly claimed lease. `read` divides
the entire bound key list into indexed probes; `history` preserves changed
versions. Network publication uses `claim_outbox`, independently verified
exact payload bytes, then `ack_outbox` with the verified hash and fence.
An overtaken generation is refused; the helper never resolves a newer
generation at save time and treats it as the preparation's original pin.

For distinct publication bodies, explicitly migrate with `--protocol 2` and
provide `payloads_json` (consumer name to exact JSON text), or programmatic
`PreparedBatch.payloads`. Its keys must equal the frozen consumer set. Each
outbox entry retains that consumer's original bytes and destination-computed
hash. Omitting the map preserves the version-1 request representation and
replay identity; the upgraded store still accepts those original requests.
The top-level payload remains required and is unused for version-2 delivery.

## Governed owner installation

Use the normal installed `mdm migrate --help` interface for the application's
registry. The owner connection selects PostgreSQL or MySQL; supply a separate,
pre-provisioned runtime account and MySQL's intended application host. The
MySQL installation requires an isolated database and its pinned catalog. It
retains immutable policy and dataset versions, catalog history and configured
vocabulary. Normal MySQL mastering remains unsupported: prepared-effect
storage is installed with runtime execution withheld until the normal merge
caller qualifies. SQL Server normal installation remains deferred.

Qualify installation through the normal owner command from an independent
five-wheel installation, then register configuration through the normal API
and read it as the restricted runtime. Test exact large integers and Unicode:
MySQL native JSON may round a configuration integer, changing its fingerprint.
Keep its canonical JSON in validated text with binary Unicode collation;
read back the original values before accepting its digest.

Qualify metadata queries over those bodies too. An unrelated large integer can
make a native JSON parser refuse a scalar lookup even when storage retained the
original bytes. Extract metadata without narrowing other values; qualify the
chosen engine's JSON text or client parsing with exact large-number cases.
Bound client reads by indexed keys and report any full-body transfer cost.

Recovery distinguishes an interrupted first installation from damage to an
initialized registry. A checksummed pending marker fences registry calls;
existing transactions drain before it is published. Retry the same build to
finish interrupted DDL. A missing installed table or immutable guard requires
restoration; a retry must continue refusing it rather than silently recreate
lost storage. Qualify populated retries, already-open runtime connections,
held transactions, exact schema/grant readback, inherited column write grants
and unchanged historical prepared-effect fingerprints. Empty helper-created
tables are not evidence of this owner workflow.

### Qualify assessed saves and owner activation

Keep an explicit pending marker while an owner installs or replaces governed
storage. Approve the catalog and retain the complete marker in the same
transaction; grant restricted runtime execution after that transaction commits.
Policy and mapping registration approve their immutable references in their
existing owner transaction. Qualify an interruption after the durable pending
marker, failed registration rollback and a populated retry. A previous runtime
grant or an already-entered call must not bypass the pending marker. A populated
native store needs a qualified data migration or a fresh rebuild before its
writer changes; installing empty replacement tables does not move its records.

An applicable assessment retains its exact prepared business intent separately
from its command and effect digest. The destination verifies ready/unapplied
state, exact intent, observed generation, approved references, versions and
checkpoint before admitting all effects atomically. Preview executes the same
validation and write assembly, then rolls back every effect. Prove both a valid
preview and a destination refusal without lasting business writes.

Keep the observing run outside assessed business intent. Materialize actual
producer metadata in publication at admission, preserve its exact bytes/hash,
and retain the original producer on replay from a different observing run.
Qualify this through the normal assessment/apply/replay API, including escaped
Unicode producer keys and late publication failure with complete rollback.

Distinguish frozen root-run pins from each command's approved input references.
Approving a mapping for one command does not establish the worker's per-run
mapping freeze. Qualify that freeze through the owning worker before claiming
it. Likewise, normal save qualification leaves operator reads, external worker
authority, publication recovery and full installed workflow as separate gates.

Retain source natural-revision and held-record identities with their original
bodies; contradictory content under the same natural key is refused. Preserve
each input occurrence even when the selected master stays unchanged. Use
configured kinds, source priorities, relationships and detail lists to test
normal saves, including competing first allocations and stale work without
identity changes. An independently installed save smoke must import the
committed bundle and native library outside the checkout; it does not replace
the installed configured-worker matrix.

## Worker authority and input publication

When a worker’s external resource lease must protect the destination commit,
explicitly select storage protocol 4 on PostgreSQL or MySQL. SQL Server retains
protocols 1–3 and refuses protocol 4 until its commit-authority path is qualified.
The normal application worker must still integrate this capability; helper
qualification alone establishes neither that integration nor engine support.

`Adapter.apply(..., authority=proofs)` takes a nonempty list of resource proofs.
Each names `resource`, positive `token`, UUID `run_id` and `attempt`, and an
explicit-timezone ISO `expires_at`. Pass authority separately from the immutable
prepared intent so a retry can refresh its proof without changing business
identity. The destination must refuse an older token, a same-token different
run/attempt, and an expired proof, including on the duplicate path.

**Expiry covers the commit.** A successful precheck is insufficient if writes
or a caller-held transaction can outlive the proof. Qualify late expiry after
writes, rollback of all effects, duplicate retry under fresh authority and
migration overlap. PostgreSQL uses a deferred commit check; MySQL owns its
transaction and refuses a caller-held transaction. Test malformed direct
requests and excess column grants as well as Python API validation. Freeze
historical protocol fingerprints before adding a new protocol.

Use `PreparedBatch.publish_inputs=True` (CLI input `publish_inputs: true`) when
new immutable inputs require publication even if current master effects stay
the same. Protocol 4 makes that choice part of the immutable intent. Repeated
identical inputs create no new delivery; index-only maintenance retains the
existing no-publication behavior. Qualify both cases and their unchanged replay.

Keep candidate routes pinned with native record-index preparation. A route
change must rebuild derived keys from the retained latest reading while
preserving its original assertion, occurrence and batch. Refuse a changed route
without that reading. Read back the frozen route fingerprint and dereference
exact immutable input keys before using indexed candidates; a pointer alone is
not the retained evidence.

### Qualify the normal read phase separately

Connect proposals through the existing Merge Stage and RecordReader boundary.
An explicit read-only Store may expose a qualified read phase before the normal
writer is ready. Exercise that public path and prove it refuses merge,
assessment and publication admission. Preserve the default write gate until the
atomic caller qualifies; an installed read-phase check does not establish full
workflow support.

Validate every index member against its own requested group. Checking membership
only against the union of requested groups can admit a record filed under the
wrong master, source or candidate value. Dereference immutable inputs, verify
stored IDs and hashes, and compare current pointer provenance with the retained
reading. A plain relationship's far end is stored state, but still requires
valid pointer provenance; validating it does not authorize replaying its identity.

Prepare relationship/review reference indexes and per-kind publication floors
in the shared native engine. Compare publication instants, retain the original
identity/time, and save derived keys atomically with their authoritative records.
Read the destination generation before the read phase; the later save must
validate it at the destination. Prove real per-key index conditions and bounded
rows beside unrelated populated entries, including bitmap index probes when
that engine chooses them.

An upgrade appends migration history and preserves populated state. Pending
state disables old entry points before procedure replacement; mutation guards
installed first also fence calls already inside a legacy procedure. Their
current locking read of the migration ledger either drains such a call before
pending or refuses its write. Do not also acquire the generation gate in the
migration barrier: that introduces an opposing lock order. Qualify actual
overlap, partial replacement, resume, old-batch replay and guard readback on
every selected engine. MySQL procedure replacement temporarily removes its
EXECUTE grant; final migration restores only the restricted grants.

MySQL's independent table options may compile in a different order in another
Python process. Normalize only those known equivalent options for stable
fingerprints. Recognize the exact historical version-1 permutations without
rewriting their ledger checksums; reject other changes and downgrade attempts.

The existing engine's environment-backed connection helper delegates driver
selection to this adapter. PostgreSQL retains its configured role selection.
MySQL and SQL Server authenticate the configured runtime principal directly;
an owner login is refused rather than impersonated. Close a rejected raw
connection before raising, because the pool has not adopted that session yet.
This connection proof does not qualify the native Store's remaining operations.

This prepared-effect API is not a drop-in replacement for the application's
native Store, Rules, Bookkeeping, reference or source-activation commands.
It supplies no second matching/identity/survivorship algorithm and accepts
no authority to approve or activate a source. Test/report those integrations
separately; passing this helper does not make a refused application command
supported.

### Retained read provenance

Read the source pointer, immutable evidence, canonical master and related rows
in one caller-held snapshot. Commit a competing save between those probes:
the first answer must remain coherent, and the next must see the new state.

Keep each object's projection generation, original producer and destination
recording time. Check existing committed event metadata before adding storage.
A different observer's replay, and a new batch with unchanged objects, must
preserve that object's original provenance even when global generation moves.

Pin pages to their requested generation, document cursor ordering, and retain
alias and retirement markers. Verify earlier pages after later merges and
object creation. Exercise the normal consumer and actual downstream master-ID
lookup from an independent installation with restricted roles. A legacy table
returning no rows does not prove a selected-store command works: identify any
uninstalled route explicitly and keep its qualification open.

## Native registry integration

The existing registrar now delegates immutable policy retention and versioned
dataset mapping reads/writes to this skill's adapter. Governance still checks
qualification, approval and protected contract parts in the shared engine.
These helpers use the caller's existing transaction and principal; they do not
connect as an owner, apply native migrations or activate a source. Frozen runs
keep their original mapping versions. Worker runtime pins include all three
adapter implementation files, which ship with the installed engine.

Consume policy and dataset content through typed adapter queries too. Raw text
queries can return undecoded JSON and a fixed schema name can select another
database on an engine without the same schema model. Policy validation stays
in the shared Merge Stage; the adapter reads the selected connection's typed
policy row and exact source contracts. The append-only original dataset
contract remains distinct from its versioned current/frozen mappings.

Keep unbounded source names as Unicode text. Where a text index has bounded
keys or database collation changes equality, index the UTF-8 digest and check
the retained exact name on readback. Put the source key before the mapping
version in its index, and prove both latest and frozen-version seeks with the
actual engine's plan.

Contain a concurrent identical registration with a savepoint, preserving the
caller transaction. On a duplicate, a shared current read sees the winner
under repeatable-read isolation. An exclusive lock upgrade can deadlock the
other duplicate registrars; force overlapping inserts in the regression test.
An unrelated integrity failure remains a failure.

Registry-operation tests on isolated tables do not qualify a native migration,
Merge Stage, control protocol or source activation. Complete those remaining
operations through the owning workflow before reporting engine support.

## Resolve the selected target

Read the operator's engine and environment separately. An all-three request
has three independent targets, each retaining its chosen engine. Resolve
private connections through their configured environment variables and check
the actual connection dialect before applying DDL or running a load:

| Selected engine | SQLAlchemy dialect |
|---|---|
| PostgreSQL | `postgresql` |
| MySQL | `mysql` |
| SQL Server Express | `mssql` |

Discover capabilities through the selected entry point's help and read back the
target's migration history, objects and grants. Record a dialect refusal as
the exact missing operation. A working connection establishes reachability;
the full caller path establishes storage and merge support.

## Map operations, keeping computation shared

For each operation below, name its current runtime entry point, selected
engine's storage mechanism and the proof that mechanism works. A missing
entry stays missing in the deployment report. The shared Rust/Python Merge
Stage interprets policy once for every engine; storage differences carry
its inputs and effects without interpreting a second business policy.

| Operation | Storage responsibility and completion evidence |
|---|---|
| Initialize and migrate | The supported migration path installs the logical objects, checksums and restricted grants; rerun and populated-store readback match the build. |
| Register governed configuration | The existing configuration owner retains genuine qualification, approval and activation evidence. The helper pins the prepared run's supplied versions; it does not implement the registration workflow. |
| Retrieve a batch's scope | Indexed, bound key collections retrieve the affected masters, records, decisions and links defined by the skill's Merge Stage scope. Each selected engine's plan proves the indexed access. |
| Prepare a proposal | Shared computation makes matching, identity, survivorship, classification and relationship decisions. The adapter preserves their values, order and provenance. |
| Commit assessed effects | The destination rechecks current state under its transaction/concurrency mechanism and atomically persists the proposal, changed effects, immutable history, checkpoint and publication intent. Competing writers cannot both commit stale work. |
| Claim and finish publication | Durable claims, server-time expiry, fencing and verified content protect delivery; network publication stays outside the master transaction. |
| Read, replay and resume | The committed generation and original frozen pins remain authoritative. Historical and current reads agree with the contract; replay changes nothing and interruption resumes retained progress. |

Use [SQL writer](../../sql-writer/SKILL.md) for portable logical models and
compiled statements through the owning migration or registration command.
Its nonportable-construct limits still apply. SQL translation alone cannot
supply a privileged operation, authorization check or concurrency primitive.
The selected database retains those authoritative guarantees; shared program
checks supplement them.

Keep integers and decimals exact, null distinct from empty, timestamps at the
contract's precision, and original canonical publication bytes and hashes
stable through write/read cycles. Verify collation and ordering where they
affect key equality. Select representations through measured contract parity,
including numeric and temporal boundaries; a driver default is not evidence.

## GoF review

Before recommending a structural change, use `gof-refactor-reviewer` on the
relevant existing code and its git history. Follow its linked evidence,
smell and adjudication steps. For a wholly new design, use
`gof-pattern-selector`. If the requested skill is unavailable, report that
limitation and perform a focused manual review.

Review the existing storage seam first: which engine-specific operations
actually change, where callers repeat those choices, and what the next
supported-engine change would cost. Keep business computation shared. An
Adapter is justified when a concrete storage API needs to fit the existing
Merge Stage contract; its name alone does not justify a wrapper, new class
hierarchy or another policy interpreter. Keep the current design when the
evidence does not justify a refactor. A recommendation names its code/history
evidence, present cost, smallest change and maintenance or migration cost.

Review the resulting work again; the initial consult does not verify its
implementation. Report three axes separately:

- **Standards:** repository rules, ownership, private connections, migration
  discipline and selected-engine handling.
- **Spec:** the operator's requested scope and each engine's actual state.
  Verify executable storage code remains in the skill and treats all domain
  differences as opaque caller data.
- **GoF:** evidence for keeping or changing the seam, costs of any proposed
  pattern, and whether a second merge algorithm or unnecessary layer appeared.

## Qualify and deploy each target

Use the parent skill's shared per-engine behavior checks on real databases
with restricted runtime roles for every affected kind and source. Compare
identity decisions, field/profile winners, links and their history,
waiting/rejected outcomes, publication content and retained hashes. Check populated migrations, grants,
lookup plans, concurrent/stale writes, rollback, lease expiry, interrupted
recovery and unchanged replay. Passing an isolated type or lock check does
not qualify a complete adapter.

Register the parity matrix in the repository's canonical CI workflow and
include it in the required aggregate gate. A separate workflow can pass
while the maintained test-folder inventory cannot see it. Reproduce the
inventory check locally; keep its coverage assertion intact.

Hand qualified configuration and supported migrations to
[Data Operations](../../data-operations/SKILL.md#apply-store-ddl). Preserve the
existing Rules approval/activation and published-reference lifecycle. A
fixture proof cannot activate a real source. Keep actual values and private
connections outside public reports.

Report each selected engine separately: migration state, requested domains'
configuration state, merge-proof scope, and any missing runtime operation or
release evidence. Leave incomplete targets explicit
while independent supported targets proceed. Qualifying the prepared-effect
adapter and activating an operational source are separate results.

The security boundary follows the engines' documented mechanisms: restricted
execution of [PostgreSQL definer functions](https://www.postgresql.org/docs/16/sql-createfunction.html),
[MySQL definer procedures and transactions](https://dev.mysql.com/doc/mysql/8.0/en/create-procedure.html),
and SQL Server owner-executed procedures. SQL Server's long JSON scalars are
read through [OPENJSON rather than JSON_VALUE](https://learn.microsoft.com/en-us/sql/t-sql/functions/json-value-transact-sql?view=sql-server-ver16).
