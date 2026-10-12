# Native engine delivery: Claude's Company work may continue

Status: Codex's merge/survivorship and collection/join blockers are cleared.
Verified 2026-10-11 after PR #920 and PR #921 merged, with all six CI jobs green
for each reviewed head. No activation or deployment is implied.

## Delivered on main

- [PR #920](https://github.com/paulananth/edgartools-platform/pull/920),
  `cd27767713ba651b6531b3ebb6ba61192d105905`: accepted identity replay and
  configured field/profile eligibility and ranking run in Rust. Public `replay`,
  `current_claims`, `select_fields` and `MergeStage` caller interfaces remain.
  Source-history folding, policy authority, canonical comparison/materialization
  and orchestration stay Python. Database checks and transactions remain authoritative.
- [PR #921](https://github.com/paulananth/edgartools-platform/pull/921),
  `3a75cfd15882d3cf8fcec520077c2a72ccbaa47d`: materialized `source.combine`
  checks/filtering, grouping, scalar ordering, distinctness, selection, missing
  matches, nested joins and drops run in Rust. Reduction was already delivered
  in [PR #911](https://github.com/paulananth/edgartools-platform/pull/911).
- The current responsibility map is
  [runtime-responsibilities.md](../../../docs/architecture/runtime-responsibilities.md).
  All source-specific/custom code stays Python; generic configured engine
  additions live in Rust behind Python callers.

## Interfaces and execution identity

Company/Bookkeeping callers retain the public worker seam:

```python
receipt = source_combine.execute(task, artifacts)
checks, reasons = source_combine.verify({**task, "candidate": receipt}, artifacts)
```

The task, manifest, `combine`/`reduce` grammar, receipt shape and `source.combined`
check are unchanged. Source extracts, contexts and lookup receipts remain
fully authenticated. Input/aggregate/output byte and row limits, valid EOF,
raw flatten bounds, no early publication and independent verification remain.
The Python facade `source_engine.combine_tables(plan, inputs, canonical)` is
internal computation over a validated plan and authenticated bounded inputs;
workers supply that authority and perform encoding/publication afterward.

New work must pin the delivered worker/facade/native binary execution digest.
Resume a frozen run using its originally pinned runtime. A new native binary
never authorizes changing an existing run's execution identity. Merge worker
runtime identity also pins evidence, identity and survivorship modules.

Payloads stay Python objects, including arbitrary integers, signed zero and
escaped surrogate metadata that can be dropped before valid output. Rust scalar
sorts release the GIL; object access/canonical callbacks hold it. Materialized
input/output objects and their costs remain.

## Qualification and practical limits

Final join-head CI [38186218511](https://github.com/paulananth/edgartools-platform/actions/runs/38186218511)
passes all six jobs: 926 engine tests (including installed bundle), 648 MDM tests,
332 real PostgreSQL integration passes plus one existing xfail, unit/architecture
and shell checks. Independent Standards/Spec/GoF reviews have no remaining findings.
The Unicode metadata finding is corrected and covered by public execute/verify.

1,500 baseline parity cases include 1,137 identical failures; inputs stay unchanged.
Forty cached Company documents in 20 two-document units, each using the complete
43,245-name cm27 census, have exact output receipts/table hashes and successful
independent verification and lost-ack retry. [RESULTS](RESULTS.md) and
[raw Company evidence](company-40.json) record timings and memory.

The 17,003,378-byte whole-census reading still has to be authenticated/decoded
and grouped on every materialized call. Preserve configured narrowing/reuse of
approved scope where applicable. Native joins do not supply Bookkeeping fan-in,
make repeated full-census loading cheap, prove new whole-census construction,
or qualify a full population/production run. Timings are provisional serial
worker measurements on a shared host; no concurrency sizing recommendation.

## Claude-owned continuation

Codex's dependency in
`.scratch/mastering-to-done/issues/20-bookkeeping-without-legacy-or-custom-code.md`
20c and L7 is removed. Continue in Claude's dedicated worktree/branch, after a
fresh fetch/rebase and overlap guard:

1. Design and implement generic Bookkeeping fan-in: a census read needs all main
   reading receipts for its bundle; each combine needs main, census and catalog
   receipts. Current `from`/expansion is a single-parent interface.
2. Express narrowed census keys through the existing authenticated derived lookup
   sets (1..256 producer readings), with versioned configuration and bounded scope.
   Preserve Company/main/catalog/census input identity and approval requirements.
3. Replace Company preparation's in-process orchestration with admitted generic
   worker steps and qualify installed empty-store replay/recovery. Keep record
   mapping retirement L7 after its active consumer proof; `workers/mdm_merge.py`
   is now released by this Codex slice.
4. Keep L8 acquisition/live SEC proof behind its existing operator authorization.

Further core ports (source-history folding, matching/quality, relationship
projection and qualifying SQL extraction) remain separately scoped work in the
responsibility map. They do not block starting this Company orchestration slice.

## Ownership release

The merged merge branch remains clean at its merged PR head. The old
`codex/responsibility-map` commit `74463d36` is retained as an archive; its
worktree now uses `codex/responsibility-map-delivered` with no changes relative
to delivered main, so it holds no shared skill/map claims. The join implementation
is merged; this final Codex handoff branch changes evidence and documentation
only. No Claude files, active workstreams or dirty shared checkout were edited.
