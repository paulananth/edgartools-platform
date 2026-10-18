# Deploy native pipelines and activate sources on the three test engines

Status: incomplete — native MySQL/SQL Server runtime support is missing;
PostgreSQL versions lack qualification evidence. This is the preflight record
from 2026-10-18 12:19 ET. Retained Company captures were found in the later
[Company readiness task](../../company-three-engine-readiness/issues/01-turn-on-company.md),
so an operator-supplied final artifact is no longer a discovery prerequisite.
That task now owns Company-first completion; Person is deferred.

The operator requested data-platform deployment of native pipeline integration and source activation for the existing Company/Person
three-engine test targets. Prior adapter PR #1073 is merged at base `059d1758`.
Preserve domain-independent adapter code inside its owning skill and use the
shared native workflow. Do not substitute an engine, fabricate proof or change
other runtimes' work. No provider requests are authorized by this task.

## Checklist

- [x] Refresh main, merged PR #1073, dedicated worktree ownership and data-platform/delegated skills; base `059d1758` — 2026-10-18 12:20 ET.
- [x] Authenticate and inspect all six databases on each selected engine; native worker profile resolves and doctor reports `ok: true`; actual initialization and activation refusals tested — 2026-10-18 12:20 ET.
- [ ] Complete source/merge qualification and acquisition evidence: three destination drafts had zero proofs/approvals at preflight. Retained Company captures were subsequently found; the Company task generates the missing proof rather than requiring an already-final release from the operator.
- [ ] Integrate native backends: MySQL/SQL Server refuse all five native store migrations and native Store construction. The generic prepared-effect helper has no native Rules/Bookkeeping/Store integration; the current deployment commands cannot complete those targets.
- [ ] Qualify the full configured pipeline for exact deployable source/merge versions. Earlier fixture/CI results are implementation evidence, not this missing release proof.
- [ ] Deploy and activate genuine qualified versions. All three current PostgreSQL activation attempts refuse `Only a proven version can activate`; no version was approved or switched on.
- [x] Independently read back unchanged PostgreSQL version/proof/approval/handoff state after refused activation; zero native MDM mappings/policies/entities/batches and ten preserved adapter tables per engine — 2026-10-18 12:20 ET.
- [ ] Verify successful activation and completed native runs/publications after prerequisites exist.
- [x] Record the three review axes, observed refusals and actual outstanding capabilities below; whitespace and overlap checks verify the operational record — 2026-10-18 12:20 ET.
- [x] Learning → skill: none. Existing data-platform/source-readiness, data-operations selected-engine gap handling and APPROVE evidence requirements already describe this boundary accurately — 2026-10-18 12:20 ET.


## Live result, 2026-10-18 12:19 ET

| Selected test server | Native store state | Activation/deployment result |
|---|---|---|
| `edgartools-test-postgres` | 40 native tables across six stores; ten separate generic adapter tables | Three drafts, zero proofs, zero approvals, zero active MDM policies/mappings. All three native activation attempts refused. |
| `edgartools-test-mysql` | Zero native store tables; ten generic adapter tables | Native MDM, Bookkeeping, Change Journal, RDM and silver initialization refuse PostgreSQL-only support; native Store constructor also refuses. |
| `edgartools-test-sqlserver` | Zero native store tables; ten generic adapter tables | Same five native migration refusals and native Store constructor refusal. |

The five migration messages are respectively `MDM requires PostgreSQL 16`,
`Bookkeeping requires PostgreSQL 16`, `Change Journal requires PostgreSQL 16`,
`RDM requires PostgreSQL 16` and `Silver requires PostgreSQL 16`.
Native Store construction says `MDM requires PostgreSQL`.

Rules activation was exercised using the current restricted Rules runtime and
selected MDM destination. Each PostgreSQL draft refused with
`Only a proven version can activate`. The version/proof/approval/handoff
readback matches its original state exactly. Native MDM has zero registered
mappings, policies, master entities and batches. One of the two source drafts
declares acquisition; neither has a recorded qualification proof. No source
records, credentials, addresses or private artifact references are published.

`edgar-warehouse workers describe mdm.merge` returns the registered worker;
`doctor` reports `ok: true` for the installed command/engine inventory. Neither
establishes target readiness; the direct authenticated native checks above
establish the actual deployment result.

Private evidence: `native-deployment-preflight-20261018.json` and its private
log under the existing test-instance directory. The checked build is current
main `059d1758`; runtime imports were directed at this dedicated checkout.
No containers, records, source versions or approvals were replaced.

## Native integration call sites

- `edgar_warehouse/workers/mdm_merge.py:58` constructs the native Store directly.
- `edgar_warehouse/mdm/clean/store.py:474` rejects other engines; `commit` calls
  native `mdm.save_batch` and publication calls native durable capabilities.
- `edgar_warehouse/mdm/clean/merge.py:145` reads native policy/state during
  matching. Its shared algorithm remains the owner of business decisions.
- `edgar_warehouse/rules/db.py:174` uses the native Rules lifecycle and registers
  approved policy/dataset versions into native MDM. The skill helper's opaque
  objects cannot substitute for these registrations.
- Native Bookkeeping, Change Journal, RDM and silver migrations have independent
  PostgreSQL guards and transaction/grant contracts. Removing guards or invoking
  the helper directly would not implement these contracts.

## Standards

Fresh branch/worktree from main, existing runtimes and data preserved. Only
this operational record is edited. No provider request, fabricated proof,
manual lifecycle write or unsupported engine substitution occurred. Private
credentials were read only by the connection setup and were not printed.
Activation refusal and unchanged state were checked against the selected live
databases, not inferred from connectivity or fixture tables.

## Spec

The requested deployment is **not complete**. Current skill commands cannot
supply the missing MySQL/SQL Server native runtime implementations. The
PostgreSQL destination also has no releasable source/merge version: current
drafts have no qualification or approval evidence. The operator's deployment
instruction is retained; it cannot supply missing test/acquisition artifacts.
A request for the existing release record or retained acquisition manifest
was sent while the independent native checks continued. Later retained-input
discovery and the merged completion guide supersede that request as a blocker.

## GoF

`gof-refactor-reviewer` is available. Existing Store/worker/merge/Rules code and
recent Store history were reviewed. Keep the Adapter boundary and shared
computation; no structural code change was made. A wrapper over the helper
cannot erase the native interface gap (governance registration, scoped reads,
worker destination fencing and durable publication). Porting the full native
store protocols requires actual per-engine implementation and full caller-path
proof. Another facade or subclass hierarchy alone would add a debugging hop
without supplying those guarantees.
