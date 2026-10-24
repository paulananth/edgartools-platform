# Independent installed MDM workflow qualification

Status: preparation started; execution incomplete.

The operator selected this gate through Lavish on 2026-10-23. This matrix
extends the [caller inventory](caller-inventory.md). It defines 18 proof
families on two target engines (36 proof slots), not 36 passing tests.
PostgreSQL and MySQL must each pass every applicable case inside each family.
SQL Server retains adapter checks; its full workflow remains later.

## Fixed proof contract

- Install all five committed bundle wheels into an isolated environment. Run
  Python with `-I` from outside the checkout. Check imported module locations
  and installed revision before opening a target. Record commit, wheel hashes,
  migration/catalog pins and configured policy/contract fingerprints privately;
  publish revision, counts, outcome and elapsed ET time only.
- Use the same immutable invented fixture/configuration on both engines. Cover
  at least two configured kinds and two sources per affected rule cohort, with
  every configured source/kind combination enumerated in the case manifest.
  Namespace, field/profile, candidate-route and relationship choices come from
  that configuration. Source priority decides field winners; equality across
  sources is not a new survivorship requirement.
- The owner provisions roles and runs normal migrations/registration. Runtime
  scenarios use the normal configured worker, Merge Stage and public readers.
  Owner-inserted identities, direct prepared-effect seeding, fake lookup
  callbacks and helper-only calls cannot stand in for normal workflow results.
- Compare deterministic expected outcomes first. Compare independently allocated
  IDs only through a verified identity crosswalk built from fixture source-record
  bindings. Never erase identity-uniqueness defects by normalizing arbitrary IDs.
- Each local invocation has a 280-second deadline. Split proof families into
  separate bounded runs. Each owns its disposable resources and stops them on
  success, failure, cancellation and timeout. CI may run the complete matrix.
- A failure or unsupported normal operation is recorded as unqualified, with
  its prerequisite ticket. Preserve the actual failure privately. No passing
  skip, swallowed refusal or forced feature flag can close a proof slot.

## Existing entry points to exercise

| Surface | Current code owner / normal call |
| --- | --- |
| Owner setup | `mdm migrate` → `clean/store.py:migrate`; `register_policy` / `register_dataset` |
| Configured worker | `workers/mdm_merge.py:execute/verify` → `clean/execution.py:execute_manifest` |
| Normal merge / assessment | `clean/merge.py:MergeStage.apply/assess/apply_assessment` |
| Run completion / observation | `clean/run.py:RunCoordinator`; `clean/store.py:Store.run_status` |
| Delivery and recovery | `clean/store.py:Store.deliver_one`; normal forced publication through `clean/cli.py:force_publish` |
| Context and contract reads | `context.py:Context`; `clean/consumer.py:ContractReader` |
| Actual master links | `silver_writer/writer.py:MdmIds`, `land` and `refresh_ids` |
| Health | `clean/cli.py:check_connectivity/counts` |

Paths under `clean/` are relative to `edgar_warehouse/mdm/`; other paths are
relative to `edgar_warehouse/`. These are existing caller surfaces, not new
procedures. Some remain PostgreSQL-specific until their owning tickets land.

## Caller and outcome matrix

| ID | Family / normal surface | Required outcomes | Prerequisite |
| --- | --- | --- | --- |
| Q01 | Independent bundle installation | Five-wheel install; no checkout imports; exact tested revision; packaged adapter/native libraries resolve | 02, 03 |
| Q02 | Normal owner migration and registration | Fresh install, repeat migration, configured policies/datasets, immutable pins, exact numeric/temporal boundaries, restricted grants | 02 |
| Q03 | Populated upgrade and recovery | Predecessor state survives; interrupted DDL fences runtime; retry completes; old batch replay and pins remain valid | 02, 04, 06 |
| Q04 | Configured worker → identifier proposal → merge | Both arrival orders; issuer-only authority; waiting records; held values; one identity per intended identity; configured cross-references | 03, 04, 06 |
| Q05 | Configured name/census/cascade proposal → merge | Both arrival orders; every configured route; held-value veto; changed routes reindexed from retained latest readings; unsupported/stale candidates refused | 03, 04, 06 |
| Q06 | Source revisions through the normal worker | Older/newer revisions, mapping changes, null/empty/zero/exact-number distinctions, complete occurrence/provenance retention and unchanged repeat input | 04, 06 |
| Q07 | Shared field/profile/kind preparation and save | Configured source priority, overrides, profile replacement/removal, kind transitions and per-source/kind case coverage; durable outcomes match expected values | 04 |
| Q08 | Normal relationship/history/detail writes | Plain far ends remain stored; configured hierarchy whole; cycle/second-parent handling; temporal boundaries; current and historical detail/relationship uniqueness | 04 |
| Q09 | Normal correction and retirement | Revoked bind, reassessment, quarantine, approved-policy lift, source retirement and replay; durable identity/history/link results remain coherent | 04, 05 |
| Q10 | Competing normal writers | Barrier-driven same-generation conflict, same-key identity/immutable collisions, one admitted winner and no lost update or partial loser effects | 04 |
| Q11 | Stale proposals and assessments | Change name/census/identity context between propose and save, including no-identity-work path; refuse/retry stale generation/effects and preserve the original assessed command | 04 |
| Q12 | Preview, duplicate and root-run association | Preview mutates nothing; exact batch replay is unchanged; changed request under same batch refuses; cross-run duplicate keeps original batch association and truthful observations | 04, 06 |
| Q13 | Normal worker destination authority | Superseded token, same-token/different-attempt, early/late expiry, duplicate retry and caller-held transaction behavior; destination protects commit, not only precheck | 06 |
| Q14 | Injected save failures | Fail each durable effect group; no partial current master, immutable input, history, detail, index, checkpoint, assessment or publication intent; retry converges | 04, 06 |
| Q15 | Worker interruption and resume | Interrupt before/after admission and commit; restore recorded immutable work and checkpoint; no silent empty-run completion; final zero-work replay is truthful | 06 |
| Q16 | Normal publication and receipt recovery | New input with unchanged master publishes when required; index-only maintenance does not; per-consumer claims/receipts, payload bytes/hash, late worker fencing and interrupted delivery recover | 06 |
| Q17 | Public master/context/history/detail and real links | Selected-engine public readers, cross-reference provenance/canonical redirect, real Silver master-ID lookup/link refresh; callback success cannot substitute | 05 |
| Q18 | Normal health/operator observations and indexed reads | Counts/connectivity/run status tell the truth under restricted roles; actual bounded per-key plans beside unrelated populated rows; no broad scans | 05, 06 |

Each family expands into named manifest cases before its execution. Record a
case per affected configured source/kind, arrival order, temporal boundary and
fault location; a single family success flag is insufficient evidence.

## Remaining execution dependencies

Normal governed storage is merged (#1152/#1153). Read-phase implementation and
skill learning are in #1156/#1155. Its independent installed smoke proves that
read API and native index preparation only.

The current default MySQL Store still refuses normal writes. Ticket 04 must
connect authoritative atomic save, ticket 05 the public/operator readers and
real master links, and ticket 06 the normal worker/authority/publication path.
Their qualification gates remain intact. The installed workflow harness must
call those normal operations after they exist; this matrix does not invent a
new command or bypass the gate.

## Evidence record

For each case: target engine, immutable configuration pin, installed revision,
normal entry point, expected outcome, actual counts/outcome, elapsed time,
private evidence location and resource-cleanup outcome. Use explicit
`not_run`, `failed` or `passed` states. This preparation records no new passing
workflow cases.
