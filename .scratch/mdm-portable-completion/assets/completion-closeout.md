# MDM completion closeout

Recorded 2026-10-28 20:14 ET against main `5c1d5b163`.

The normal configured MDM workflow on PostgreSQL and MySQL is qualified. This
record reconciles stale tickets against merged implementation and current
independent installation evidence. It changes no runtime, policy, source state,
store, historical migration or installed matrix.

## Qualified revision

[PR #1210](https://github.com/paulananth/edgartools-platform/pull/1210) merged as
`5c1d5b163`; all **20** checks pass at runtime/test head `5b51bc4a`.
[CI run 40783186458](https://github.com/paulananth/edgartools-platform/actions/runs/40783186458)
finished 2026-10-28 19:02 ET in 10 minutes 22 seconds. Its artifact verification
finds **160 cases per engine**, **two configured kinds**, **18 families per
engine**, exactly one canonical outcome per expected case, equal configuration
pins and verified cleanup. The installed revision contains the qualified head.
[Machine-readable evidence](completion-evidence.json) records the tested heads.

The earlier retirement revision had 164 installed cases per engine. Four
current/history duplicate entry points per engine were removed in #1210; their
complete assertions remain in the producer case. Every qualification family is
retained. Case-count reduction is separate from runtime speedup.

## Record qualification

[The closeout record CI](completion-record-ci.json) passes all 20 checks at `74896164` in run 40793162573, with 160 installed cases per engine, all 18 families, equal pins and cleanup. A clean rebase preserves that patch; the following changes only record this receipt and resolve the publication checkboxes. PR #1212 retains a final-head CI gate before readiness and merge.

## Obligation reconciliation

| Obligation | Qualified caller and boundary | Merged work |
|---|---|---|
| Owner installation and approved registry | `store.migrate` selects the normal owner path; `prepared_registry.initialize` installs indexes, retirement and registration before runtime admission | #1152, #1190 |
| Configured matching and scope | `catalog` pins kinds, profiles and reference/record selectors; `matching` passes those selectors to shared native comparison and indexed `RecordReader` probes | #1156, #1159 |
| Atomic assessment/save and identity/history/details | `MergeStage` uses the governed adapter; destination validates current generation, references, admission, authority and all durable effects | #1159, #1171 |
| Public reads and real master links | `ContractReader`, Context, inspection, search and `MdmIds` share the normal selected-engine read boundary | #1164 |
| Worker and publication recovery | Normal worker/verifier processes retain immutable mappings, original producers, per-consumer delivery, lost-acknowledgement retry and zero-work replay | #1171 |
| Whole installed workflow | Merge, readers, boundaries and workers run outside the checkout, with five package revisions/import paths checked | #1178, #1190, #1210 |
| Superseded implementation retirement | Owner retirement removes 34 legacy business routines; runtime AST rejects their calls; the populated-owner test preserves rows, constraints, restricted grants and replay | #1180, #1190 |

The configured-vocabulary proof exercises two invented kinds and sources on
each engine; candidate namespaces, record fields, eligibility, addresses and
reference-table selectors come from the pinned catalog. Published versioned
primitive identifiers retain their compatibility spelling; selectors and
eligibility are configuration data. The audit does not claim that every
historical filename or compatibility identifier has been renamed.

The executable boundaries remain the existing Merge Stage, record reader and
skill-owned storage adapter. Historical migration text is preserved. The
original 4,874 SQL source lines are an installation-history measure, not active
business logic. The original 36-routine inventory now retains exactly two
integrity guards; generated atomic storage and configuration-registration
capabilities enforce storage authority separately from that legacy inventory.

## Learning accounted for

All owning-skill changes were published separately: #1150 (destination
freshness/publication/reindexing), #1153 (owner installation), #1155 (read
admission), #1158 (assessed save), #1165 (read/search/provenance), #1173
(worker/publication recovery), #1179 (independent installed proof) and #1191
(registrar/verifier duties and current reads). All are merged. #1165 returns no
historical PR check metadata; this record infers no historical pass count for
it. Current full CI covers its merged guidance.

No new engine procedure was learned by reconciling these records. The separate
test-retirement follow-up still owns its five-whys guidance, obsolete test
pointer and two deferred test deletions. Those remain explicit in that ticket;
this record does not edit the overlapping skill or activation-test files.

## Scope limits

- SQL Server retains its adapter checks; its full normal MDM workflow remains
  a later qualification gate.
- MySQL uses the qualified owner registration path. The delegated registrar
  extension is qualified for PostgreSQL only.
- Silver's complete type/link/registration/mode qualification remains open in
  the parent plan. Real MDM lookup used by Silver is qualified separately.
- Broader Rules/Bookkeeping conversion, hosted migration, master onboarding,
  approval, source activation and cutover remain separate.

## Standards

Fresh Codex worktree from current main; six stale child records reconciled;
counts/outcomes and code references only. Runtime, rules, CI and historical
migrations are unchanged. Prior installed proof is carried forward because the
qualified code is unchanged. Markdown links, JSON, checklists, whitespace and
the overlap guard are the local record checks. Full final-head CI remains the
publication gate for this closeout PR.

## Spec

This closes the documented normal two-engine MDM obligations and accounts for
all separate skill work. It preserves remaining platform, Silver, hosted and
activation gates. Earlier incomplete/draft statements remain inside their dated
historical checkpoints, with current resolved headers and this evidence record.

## GoF

The available `gof-refactor-reviewer` method was applied to the current caller
inventory and Store/matching/scope history. The merged replacement already
removed parallel native read/save paths. Reuse the Merge Stage facade and
Adapter boundary. No runtime refactor, class hierarchy or new policy owner is
justified by this documentation reconciliation.
