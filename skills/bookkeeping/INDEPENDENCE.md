# Loader-independent control contract

Read this when planning/changing execution, validating control independence,
or running/recovering work under the Bookkeeping skill.

## Responsibility

Control owns work identities, dependency readiness, leases/fencing, bounded
retry, checkpoints, accounting, generic child manifests and control delivery.
External workload workers own source reading, transformations and destination
writes. External destination verifiers own domain checks and readback.

Only a fixed, authenticated task protocol crosses this separation. Pass frozen
specification/input/output references and narrowly scoped authority messages.
Workers receive no Bookkeeping object, SQL engine, registry or private methods.
The controller has no domain callbacks or domain-operation name branches.
Approved profiles pin worker/verifier runtime and contract digests; authoring
YAML cannot supply an arbitrary import path or shell command.

The [replacement design](../../docs/research/bookkeeping-loader-independent-design-2026-10-02.md)
defines the proposed protocol and transition rules. Follow its failure and
recovery requirements; loader replacement is not a prerequisite for removing
control coupling. Existing loaders may remain inside external worker processes.

## Current gap

At the inspected baseline, `configured_bookkeeping()` imports Company and MDM
integrations. `runner.run()` invokes execute/reconcile callbacks with the whole
Bookkeeping object; completion calls a registered verifier. Company capability
code imports Silver, and Journal conversion branches on domain operations.
This is coupled execution. The proposed fixed task path is not implemented.

Existing commands remain useful evidence about the old path. Do not present
their success as independence, add another source callback, or silently fall
back to that path when the request requires this contract. Report unsupported
execution/recovery explicitly while continuing permissible read-only inspection,
control-store work and planning. Preserve exact retained evidence for old runs.

## Audit and qualification

Inspect actual construction and transitive imports, not only operation names:

```bash
rg -n 'loaders|parsers|silver|mdm|company|Capability|registry|importlib|__import__' \
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
completion. Admit authenticated reports from the frozen verifier profile with
exact work/input/spec/runtime/candidate bindings, required check coverage and
destination proof references. Recheck live authority before marking work
verified and releasing dependents. Lost leases reject old completion.

Record verification scope precisely: skill validation, helper isolation,
control runtime acceptance, domain output qualification and deployment are
different results. Stop calling the design implemented until its acceptance
gates have actually run.
