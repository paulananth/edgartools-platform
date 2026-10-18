# Turn on Company through one configured engine on three databases

Status: incomplete. Scope: Company only on the existing PostgreSQL, MySQL
and SQL Server test instances. Person is deferred until this entity completes.

The operator requires the same engine and business configuration on every
database, with no Company-specific code or hardcoded entity behavior. Keep
database storage differences in the existing skill-owned adapter boundary.
The operator further limited step 1 to repairing the existing shared engine
and existing adapter, with no additional implementation/framework. This
readiness record introduces no engine or adapter changes.
This work first establishes what configuration can complete and identifies
missing generic native operations without bypassing their protections.

## Checklist

- [x] Refresh current main `a115c725`, selected database state and isolated worktree ownership; authenticated live readback and overlap guard passed — 2026-10-18 13:51 ET.
- [x] Locate Company source/current policy, destination drafts and retained captures; exact source body/digest matches its destination draft, policy does not; five receipt-authenticated inputs checked below — 2026-10-18 13:51 ET.
- [x] Check configured profiles and native readiness on all three engines; six declared profiles expose execute/verify, PostgreSQL native store constructs and cross-reference capabilities exist, other engines refuse native Store construction — 2026-10-18 13:51 ET.
- [x] Run bounded existing name-key qualification on five real captures (seven names); exact configured/retained parity passes. Run affected Company preparation and native PostgreSQL cross-reference checks: 26 passed in 31.96 seconds — 2026-10-18 13:51 ET.
- [ ] Run the supported common configuration path where available and retain its measured qualification separately from fixture tests.
- [x] Identify exact generic native integration and source-independent submission prerequisites below; audited Store/worker/Rules callers and their history — 2026-10-18 13:51 ET.
- [ ] Integrate and qualify native target adapters with the common pipeline, Rules, Bookkeeping and Change Journal; preserve identical computation/configuration on all three engines.
- [ ] Replace the Company-specific manifest preparation requirement with generic configured submission, and qualify required dependencies through that path.
- [ ] Complete the configured next-version Company lookup-only cross-reference mapping without mutating the approved original source contract.
- [ ] Present the tested Company release and reuse applicable approval or obtain the missing exact-version approval.
- [ ] Activate and process Company on all three engines, verify native cross-references and publication, and prove unchanged replay does no work.
- [x] Report Standards, Spec and GoF review with evidence and every remaining dependency below — 2026-10-18 13:51 ET.
- [x] Learning → skill: none. The merged data-platform completion guide already distinguishes helper fixtures from native integration, requires input discovery and cross-reference qualification, and routes missing native operations to their owners — 2026-10-18 13:51 ET.

## Evidence

## Current state

Read-only checks against the actual selected databases, using Python from
current main `a115c725` at 2026-10-18 13:48 ET:

| Target | Native store state | Company turn-on |
|---|---|---|
| PostgreSQL | 40 native tables across six databases; native MDM Store constructs; cross-reference view/function present with zero rows | Source draft matches current source configuration; merge draft differs from current policy; both lack proof and approval. Zero native mappings, policies, masters and batches. |
| MySQL | Zero native tables across the six databases; ten separate skill adapter tables | Native MDM Store refuses `MDM requires PostgreSQL`. No native source registration/processing available. |
| SQL Server | Zero native tables across the six databases; ten separate skill adapter tables | Same native refusal and missing caller path. |

All targets retain their ten skill adapter tables. The adapter's earlier
three-engine qualification remains implementation evidence; it is not an
activated Company source or a complete native pipeline.

Two retained deliveries were found locally: 7,000 main documents plus one
catalog receipt, and 76,230 main documents plus one catalog receipt. The
bounded check authenticated five capture members against their receipts and
proved seven names through the existing name-key recipe. It did not read or
qualify the full deliveries. No provider request or source activation occurred.

The older installed 6,414-Company proof's whole-policy digest differs from
today's policy. Its passing counts cannot be presented as a proof or approval
of current policy without establishing equivalence for the changed content.
No genuinely applicable destination release proof/approval was found.

Private evidence: `company-readiness-20261018.json`,
`company-name-keys-5-20261018.json` and
`company-configured-components-20261018.log` under the existing private
test-instance directory. Private paths, records and connection values stay
outside this repository.

## Completion order and configuration boundary

1. **One common engine, generic native storage integration.** The existing
   `skills/mdm-engineering/scripts/database_adapter.py` owns portable prepared
   effect persistence. Native `workers/mdm_merge.py` still constructs the
   PostgreSQL-only `mdm/clean/store.py::Store`, while Rules registers policy
   and dataset versions through native MDM operations. Integrate the same
   operations for every selected engine, including scoped/indexed state reads,
   registration, atomic lease/fence checks, commit verification and publication.
   Bookkeeping/Rules/Change Journal also require their native protocols on the
   selected engine; RDM and silver need theirs where the declared delivery
   actually uses them. An address or dialect setting cannot implement these
   absent operations. Keep adapter differences in the owning skill and
   business computation shared. Do not copy Company logic into dialects.
2. **Submit configured work without an entity-specific preparer.** The current
   source declares standard read/combine/prepare/merge/journal workers, but its
   input still comes from `mdm prepare-clean-company` and
   `mdm/clean/company_prepare.py::write_company_manifest`. That module imports
   `sec_company` constants and fixes the source, table, dataset, recipe list
   and publication shape. This does not meet the operator's configuration-only
   entity onboarding requirement. Supply these through the common configured
   submission path, including frozen dependency inputs and changed-file
   selection, before claiming this boundary complete. Remove the need for the
   special caller rather than creating three copies of it.
3. **Complete the Company mapping as configuration.** The current contract has
   one binding identifier namespace and zero lookup-only namespaces. Its
   existing comment explicitly defers the approved lookup-only EIN/stated-LEI
   treatment to the next source code, `sec.submissions.company.v2`; preserve
   the immutable original contract. Qualify what the retained input actually
   carries and the configured read emits, map applicable lookup-only values
   separately from identity identifiers, and prove indexed lookup, multiplicity,
   unbound rows, canonical redirects and provenance on every engine. Map no
   identifier the source does not state. Keep this in rules, without entity
   branches in shared engine/adapter code.
4. **Pin and qualify one release on all three databases.** Use identical source
   and policy content and the same authenticated retained inputs. Account for
   accepted/waiting/rejected records, dependency scope, acquisition completeness,
   recovery and unchanged replay. Start with a small genuine captured sample,
   then the declared retained delivery. Record current source/merge proof;
   component tests or old-policy results do not supply it.
5. **Approve, activate and verify.** Present the tested content and measured
   outcomes, reuse genuinely matching approval or obtain exact-version approval,
   then activate merge before source, run the common workflow, independently
   verify MDM/Journal/publication and prove an unchanged repeat starts no work.

The shared integration and source-independent submission gaps are engineering
prerequisites. Company mapping and merge policy remain configuration. The
current release cannot satisfy the whole three-database request by changing
configuration alone. No runtime implementation was changed in this readiness
pass, and no unsupported native path was substituted with helper persistence.

## Standards

Dedicated fresh Codex branch/worktree; unrelated runtime changes and all
persistent servers preserved. This ticket contains the maintained checklist.
No secret, database address or source record was printed or committed.
Targeted testmon checks completed within five minutes. The fixture-owned
PostgreSQL container was removed by its fixture; other runtimes' containers
were left alone. No manual governance write, fabricated proof or approval.

## Spec

Company is the sole entity under work. The requested end state is a shared
configured engine with equivalent behavior on all three databases, plus
verified native activation/delivery. This is incomplete: generic integration,
generic submission, next-version cross-reference mapping and current release
qualification/approval/activation remain open. Person is deferred.

## GoF

`gof-refactor-reviewer` is available and its method was applied to existing
Store/worker/adapter construction, the source-specific preparer and their git
history. Keep the existing Adapter boundary; it already isolates proven
storage differences. Its current interface does not supply the native
registration/run-control protocol, so an extra facade or hierarchy cannot
replace implementation and caller-path qualification. Shared configured
submission should take source-specific values as data; adding a Company
strategy or per-database Company subclass would violate the requested seam.
No runtime code or pattern refactor was made in this pass.
