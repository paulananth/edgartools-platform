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

This prepared-effect API is not a drop-in replacement for the application's
native Store, Rules, Bookkeeping, reference or source-activation commands.
It supplies no second matching/identity/survivorship algorithm and accepts
no authority to approve or activate a source. Test/report those integrations
separately; passing this helper does not make a refused application command
supported.

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
