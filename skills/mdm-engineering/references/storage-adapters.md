# Storage adapter contract

Use this reference for PostgreSQL, MySQL or SQL Server Express selection,
missing storage support and the GoF review of that boundary. The adapter here
is an instruction contract within MDM engineering. It contains no executable
adapter and installs no runtime capability. A request to change these
instructions does not authorize adding adapter code or scripts elsewhere.

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

Discover capabilities through the installed command's help and read back the
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
| Register governed configuration | The same source, mapping, merge-policy and reference pins retain genuine qualification and approval evidence. Runtime cannot register an unapproved replacement. |
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
  For instructions-only work, verify the diff contains instructions only.
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

Hand qualified configuration and supported migrations to
[Data Operations](../../data-operations/SKILL.md#apply-store-ddl). Preserve the
existing Rules approval/activation and published-reference lifecycle. A
fixture proof cannot activate a real source. Keep actual values and private
connections outside public reports.

Report each selected engine separately: migration state, requested domains'
configuration state, merge-proof scope, and any missing runtime operation or
release evidence. Leave incomplete targets explicit
while independent supported targets proceed. This instruction contract is
neither an installed adapter nor evidence of a completed deployment.
