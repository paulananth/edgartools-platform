# Loader-independent control contract

Read this when planning/changing execution, validating control independence,
or running/recovering work under the Bookkeeping skill.

## Responsibility

Control owns work identities, dependency readiness, leases/fencing, bounded
retry, checkpoints, accounting, generic child manifests and control delivery.
External workload workers own source reading, transformations, destination
writes, and the domain checks and readback of what they wrote.

Only a fixed, authenticated task protocol crosses this separation. Pass frozen
specification/input/output references and narrowly scoped authority messages.
Workers receive no Bookkeeping object, SQL engine, registry or private methods.
The controller has no domain callbacks or domain-operation name branches.
A run pins each profile's worker runtime digest; authoring
YAML cannot supply an arbitrary import path or shell command.

## Status

The callback registry, the per-source, MDM and source-input modules, the
acquisition and source-evidence callbacks and the Journal branches on operation
names are deleted. Control hands out task envelopes and accepts workers' check
reports (`bookkeeping claim`, `renew`, `report`, `fail`, `finalize`); workers run as their own processes
(`edgar-warehouse workers`).

| Gate | State |
| --- | --- |
| 1. Control starts and builds every command with domain packages blocked | Passed: the control-only wheel (`packages/bookkeeping`) installs with the Journal wheel and no domain distribution, and its own CLI, in isolated mode, makes every control call of a run (migrate, grant-profile, claim, report, finalize) on PostgreSQL 16; submission is Rules' job (`tests/integration/test_bookkeeping_wheel_postgres.py`); an import guard also covers the repository's control (`tests/architecture/test_bookkeeping_control_only.py`) |
| 2. Two workers on one protocol, no Bookkeeping change between them | Passed: `artifact.copy` and `jsonl.count`, in their own processes (`test_two_workers_in_their_own_processes_complete_a_cli_submitted_run`) |
| 3. PostgreSQL 16 restricted roles: issuer authorization, wrong bindings, forged checks, conflicting reports | Wrong bindings, an output outside its intended place, forged or missing checks, a conflicting report and stale or missing fencing are refused (`test_a_report_that_names_other_work_*`, `test_a_candidate_must_be_*`, `test_restricted_functions_*`, `test_renewal_takeover_*`). A run freezes each step's profile; only a login of that profile's worker role claims and completes its units (`test_only_a_profiles_worker_*`) |
| 4. Recovery: lost acknowledgement, crash after commit, lease expiry, changed runtime, Journal outage | Lost acknowledgement, crash after commit, Journal outage, a changed runtime and resource checkpoints across runs are covered. A lease lapsing before the report refuses it, and the next attempt completes the unit (`test_a_lease_lapsing_*`) |

A kind or source whose step has no worker profile yet (no key in `PROFILES`,
`edgar_warehouse/workers/__init__.py`) is reported unsupported, naming the
ticket that builds it; never add a callback back into control.

## Audit and qualification

Inspect actual construction and transitive imports, not only operation names:

```bash
rg -n 'loaders|parsers|silver|mdm|<each source or kind module name>|Capability|registry|importlib|__import__' \
  edgar_warehouse/bookkeeping skills/bookkeeping
```

Search matches guide inspection; absence of a match is not proof. Before
claiming loader-independent execution, require:

1. A control package whose dependency closure excludes domain implementations
   and parser libraries. Start the real controller with these packages absent
   or their imports actively blocked; exercise CLI construction and control
   lifecycle. Check dynamic/transitive imports as well as static imports.
2. Two distinct external workers using the same protocol without changing
   Bookkeeping code or registering domain callbacks. Domain output tests belong
   to those workers; they must retain existing interpretation assertions.
3. Mandatory PostgreSQL 16 acceptance with restricted roles for stale fencing,
   issuer authorization, wrong task/input/spec/runtime bindings, missing check
   coverage, corrupt evidence and conflicting completion reports. No skips for
   missing prerequisites.
4. Separate recovery cases for lost acknowledgement, crash after destination
   commit, lease expiry during verification, missing pinned runtime and Journal
   outage. Reconciliation precedes repeat execution; destination authority must
   be checked at mutation time. Resume revalidates destination evidence.

Source/feed descriptor resolution is allowed: read approved configuration and
return opaque identities/hashes. Test the helper with loader/domain imports
blocked. That proves helper isolation only, not independence of the controller.

## Evidence admission

A worker exit code, report flag or output hash does not prove destination
completion. Accept a report only from a login of the frozen worker profile, with
exact work/input/spec/runtime/candidate bindings, required check coverage and
destination proof references. Recheck live authority before marking work
verified and releasing dependents. Lost leases reject old completion.

Record verification scope precisely: skill validation, helper isolation,
control runtime acceptance, domain output qualification and deployment are
different results. Stop calling the design implemented until its acceptance
gates have actually run.
