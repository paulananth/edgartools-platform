# Complete native Company activation on three database engines

Status: claimed. Company only; Person remains deferred.

## Scope

Implement the operator's existing-engine/adapter repair in existing runtime and
skill files. Use the same configured merge behavior on PostgreSQL, MySQL and
SQL Server. Keep storage implementation in the existing skill-owned adapter;
do not add another pipeline, framework, domain strategy or runtime module.
Remove database-specific business computation when its existing storage
boundary is repaired. Verification may extend existing tests.

Preserve Claude's Rules CLI and unpublished proof runner. The revised planned
file guard passes without those files. No provider access is authorized.
Changes to configuration, activation and production remain subject to the
existing exact-version qualification and approval contract.

## Checklist

- [x] Reconcile current main, source configuration, retained-input evidence and ownership; authenticated live checks confirm 40 native PostgreSQL tables across six databases and zero native tables on the other engines; all persistent servers and other runtimes preserved — 2026-10-18 18:44 ET.
- [x] Review existing engine/adapter/Rules/control history and GoF costs before changing code; retained the existing Adapter boundary and plain functions; no subclass hierarchy or second pipeline — 2026-10-18 18:44 ET.
- [ ] Characterize existing behavior and demonstrate each repaired native capability gap with a failing test.
- [ ] Repair shared engine operations and existing skill adapter integration for registration, scoped/indexed reads, atomic writes, restricted roles and native verification.
- [x] Remove the Company-specific source-priority check; 51 survivorship tests and six PostgreSQL Company/run-pinning integration tests pass — 2026-10-18 18:44 ET.
- [x] Move native policy/dataset registration and frozen mapping reads into the skill adapter; the same real-database test passes on PostgreSQL (1.50 s), MySQL (1.07 s) and SQL Server (2.95 s), including rollback, repeat, concurrent policy registration and read-only mastering-role refusal. This is registry-operation evidence, not native migration or activation proof — 2026-10-18 18:45 ET.
- [x] Fix the Standards review's exact-key portability finding: retain unbounded Unicode source names and use UTF-8 hash keys on engines with bounded/default-collated text indexes. The same check proves long Unicode, case and accent distinctions on all three engines — 2026-10-18 18:56 ET.
- [x] Force four simultaneous policy inserts; reproduce and fix MySQL's duplicate-key lock-upgrade deadlock by using a shared current read. The strengthened registry check passes on PostgreSQL (1.44 s), MySQL (1.51 s), SQL Server (2.26 s) — 2026-10-18 18:56 ET.
- [x] Fix follow-up key ordering and require actual key-seek plans for latest and frozen mappings; PostgreSQL, MySQL and SQL Server checks pass (1.41 s, 1.48 s, 2.56 s). The ordinary application wheel now includes the canonical adapter; an isolated import outside the checkout resolves and pins all three resource files — 2026-10-18 19:07 ET.
- [x] Document the registry-operation boundary, exact source keys, source-leading index and duplicate-insert shared-lock lesson in the existing storage-adapters skill reference — 2026-10-18 19:07 ET.
- [ ] Repair Rules, Bookkeeping and Change Journal storage operations required by the declared native pipeline; preserve approval, lease/fence, recovery and publication enforcement.
- [ ] Remove source/entity hardcoding from the common execution path using existing configured operations.
- [ ] Qualify the same pinned Company configuration and inputs on PostgreSQL, MySQL and SQL Server; verify parity, rollback, concurrency, interrupted resume and unchanged replay.
- [ ] Establish applicable exact-version approval, activate Company on the three selected test databases and independently verify native state and publication.
- [ ] Review Standards, Spec and GoF; fix findings and run affected tests plus final CI.
- [ ] Commit and publish the reviewed change in a PR; report exact checked head and remaining work accurately.
- [ ] Learning → skill: update relevant existing instructions to match the qualified implementation.

## References

- [Earlier readiness and retained-input evidence](../../company-three-engine-readiness/issues/01-turn-on-company.md).
- [MDM engineering](../../../skills/mdm-engineering/SKILL.md).
- [Storage adapter boundary](../../../skills/mdm-engineering/references/storage-adapters.md).

## Ownership check

An initial speculative path list included the Rules CLI and the old proof
runner. Its planned-file check reported Claude's worktree on those paths.
The repair excludes both; the narrower planned-file guard passed. This is
not permission to edit or adopt that runtime's unpublished changes.

## Implementation checkpoint

Native registration now calls the existing skill adapter, with shared policy
validation retained in the engine. Registry tables are logical SQLAlchemy
models; no operational migration has been applied by this change. Isolated
real-database tests create their own temporary registry tables and exercise
the actual native registration caller, frozen reading selection and rollback.
They do not qualify the native migration, Merge Stage, control protocol or
source activation. PostgreSQL retains its current migrations and guards.

Worker runtime pins now include the three canonical adapter implementation
files. The adapter remains importable as a standalone skill resource and from
the installed data-skill bundle. No entity/source policy moved into it.

## Checkpoint review

### Standards

The independent review of `1b156a31..59b2c045` found one portability defect:
bounded/default-collated source keys. The follow-up replaces those keys as
described above and adds actual-engine regression cases. Other documented
standards passed for that checkpoint. Follow-up review remains pending.

### Spec

Independent review found no implemented-slice defect or extra pipeline/
framework, and explicitly classified the overall activation as incomplete.
The unchecked native integration and activation parts above remain required.

### GoF

The existing Adapter seam remains appropriate. Plain storage functions remove
vendor casts from the existing governance caller without introducing another
class hierarchy. Its cost is an explicit dependency on the skill resource;
installed-resource resolution and worker runtime pins must be qualified with
the remaining installed-path tests. No pattern is added to merge computation.
