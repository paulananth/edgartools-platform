# Source Extract evidence behind its owning module

Design only. Inspected origin/main `a01719c43` on 2026-10-17. The operator agreed to the ownership split and to opening one Source Extract, inspecting authenticated evidence, then iterating tables from the same private snapshot. Implementation authorized by the operator on 2026-10-17, together with Relationship Interval ownership. No runtime implementation, behavioral qualification, provider request or store change is included in this design.

## Outcome

Name Frequency no longer calls `source_readings._index`, fabricates a version-3 worker request or calls `source_read._lookups`. One Source Extract interface owns reading-format knowledge, receipt authentication, pinned contract access, lookup resolution and bounded ordered table iteration. Name Frequency retains its domain decisions and final publication authority.

The snapshot is the authenticated private index and its receipt references, not an eager copy of every partition or the original captured source. Partition bytes remain authenticated as iteration advances. Opening an extract does not prove that all its tables have been consumed.

## Module and interface

Deepen `edgar_warehouse/workers/source_readings.py`. Use ordinary functions and one small state-owning representation; final names are implementation choices. Do not add a registry, interchangeable-reader hierarchy or a new storage adapter. The existing injected Artifacts adapter remains sufficient for production and local fixture tests.

The new interface provides:

1. Open an immutable reading reference with the existing Artifacts adapter, explicit aggregate table byte/row budgets, explicit contract-byte bound and explicit permission to consume lookup-bearing evidence. Authenticate and decode the bounded index once, retaining a private copy. Authenticate and parse its pinned contract, where present, using the existing Rules loader. Absence of contract evidence remains distinguishable so the consumer can require it.
2. Inspect defensive copies of the reading identity, pinned contract and original-artifact evidence needed by the consumer: input/context/lookup references, source record count and expanded bytes where declared. Partition traversal bookkeeping remains private. Do not fabricate absent evidence for older inline readings.
3. Resolve an original artifact's declared lookup sets on demand through the same module, against that private contract/input evidence. Return caller-owned values without allowing their mutation to change traversal. Authenticate before returning values. The consumer need not know worker-manifest versions. Keep lookup resolution lazy enough that the consumer can perform its existing recipe/count checks before resolving the wanted set.
4. Iterate the existing ordered chunk events from that same private index, with the same original artifact indices, identities, table/deferred rows and cumulative table byte accounting. Avoid reopening the index through `iter_load`. Rows remain provisional until successful exhaustion. Use one forward traversal per opened extract; a caller wanting another complete pass opens another extract.

The module does not publish a census, approve a recipe, interpret provider publication metadata or compare the wanted set to a business population. It does not reparse the captured source, authenticate an archive by downloading it, or assert that every referenced source byte was reread. Authentication claims cover the existing receipt chain actually checked.

## Shared lookup implementation

Move the reusable lookup-document authentication and derived-set resolution now in `source_read._lookups` and `_derived_sets` to their owner beside reading traversal. The source.read worker retains worker-manifest validation, input/context shape checks and input version requirements, then invokes the common lookup operation with the validated input and receipt. The opened Source Extract invokes the same implementation directly from its evidence.

Keep one implementation, with no import from the reading consumer back into the source.read worker. A narrow module operation for the worker is acceptable; the Name Frequency caller only needs its opened extract. Preserve raw scalar/pair sets, derived producer readings, exact input binding, declared-set equality, raw-value accounting, UTF-8 bounds and aggregate lookup limits. Derived producer readings must finish successfully before a lookup set can be returned. No deduplication may evade raw count or byte bounds.

Do not conflate three existing version schemes: reading documents use versions 1/2, lookup documents use versions 1/2, and the source.read input manifest supports version 3. Their meanings and accepted values remain unchanged.

## Name Frequency duties

Keep `_gleif` responsible for these existing decisions, in their existing sequence where observable:

- Validate publication metadata and require a full Golden Copy, not a delta.
- Require contract evidence and compare its parsed contents with the exact configured census recipe.
- Require exactly one original artifact and compare its source record count with publication metadata.
- Ask the opened extract for authenticated lookup values and require its wanted names to equal the SEC population's wanted names.
- Derive the same census provenance from existing evidence and stream tables into the existing census calculation.
- Publish the final file only after complete successful consumption. On late corruption, budget failure or cancellation, publish no new result and preserve an existing result.

The newly merged Company cascade preparation, configured combination, contract normalization, activation rules and census calculation remain outside this refactor. Retain their tests when checking the touched Name Frequency caller.

## Compatibility and resource constraints

- Preserve accepted reading formats, source identities, ordering, empty-source schema, deferred records, exact lookup values, census bytes and provenance.
- Preserve explicit lookup opt-in. Receiving a lookup receipt is not a declaration that its values have been authenticated; the new operation makes that distinction explicit.
- Preserve bounded index size, per-partition limits and aggregate table byte/row accounting across all original artifacts. Count the private index once in that accounting.
- Contract, lookup-receipt and derived-reading bounds retain their current distinct accounting. Do not silently combine previously separate budgets or loosen any existing bound.
- Preserve lazy partition reads and bounded memory: retain the private index, the current decoded partition and lookup data already permitted by existing limits; do not materialize the whole partitioned reading. Inline readings retain their current bounded whole-document behavior.
- Preserve caller isolation: changing the input receipt, exposed metadata, contract, lookup values or chunk metadata cannot redirect authenticated iteration.
- Preserve error categories and relied-on diagnostics, cancellation propagation and refusal ordering where callers rely on it. Pin observable rejection behavior before moving validation. Unrelated malformed-input hardening requires separate evidence and scope.
- Existing `load`, `iter_artifacts` and `iter_load` retain their documented behavior. In particular, the materializing inline loader currently differs from incremental iteration in validation and budget handling; do not tighten legacy callers as a side effect of reuse.
- Update every affected runtime fingerprint to include the moved implementation and its actual dependencies. Test fingerprints through the owning runtime interface; do not merely inspect a list of filenames. Changed code is not relabeled with an old runtime digest.
- No Rust, rule-document, command, receipt-schema, database, deployment or shared-store changes are required. Database enforcement remains at the destination.

## Verification through the interface

Use invented local fixtures and the existing Artifacts adapter. Establish the affected baseline first; every local test invocation uses testmon and finishes within five minutes. CI performs broader verification. No provider access is needed.

- [ ] Prove opening and iterating inline and partitioned readings preserves existing table events, source identities, bytes and rows, including empty inputs and multiple artifacts.
- [ ] Prove the opened view uses one authenticated private index and later partitions remain unopened until requested.
- [ ] Prove mutations of original references and returned evidence, contract, lookup values and chunk metadata cannot redirect iteration or alter later events.
- [ ] Prove scalar/pair and inline/derived lookup sets preserve exact input binding, declared-set equality, raw count/UTF-8 and aggregate limits; retain worker version checks and independent verification coverage.
- [ ] Prove malformed final partitions, gaps, count/byte/schema faults, aggregate budget failures, early stop and cancellation never establish complete consumption.
- [ ] Retain Name Frequency wrong-population, wrong-recipe, missing/invalid metadata, delta-publication and record-count rejection cases, with unchanged canonical output for valid inputs.
- [ ] Add a Name Frequency late-corruption case proving no new file is published and an existing file is unchanged.
- [ ] Retain Company cascade and classification coverage added in the newer main; do not remove cases merely because they are outside the extracted mechanics.
- [ ] Prove existing public loaders preserve their distinct compatibility behavior and explicit lookup opt-in.
- [ ] Prove affected runtime fingerprints change when moved code changes; exercise an installed configured extraction/verification path if dependency movement affects packaging.
- [ ] Review Standards, Spec and GoF on the implementation; run overlap guard before each commit/push and obtain full green CI. Merge requires the operator's explicit words naming the PR.
- [ ] Learning → skill: assess implementation findings; none from this design-only review.

Existing coverage includes `tests/mdm/test_clean_name_frequency.py`, `tests/engine/test_incremental_readings.py`, `tests/engine/test_partitioned_reading_consumers.py`, `tests/engine/test_source_lookup_receipts.py` and `tests/engine/test_source_lookup_sets.py`. Migrate tests reaching retired private mechanics to the actual owning interface; retain independent worker/consumer proof and distinct failure cases.

## Implementation sequence

1. Create a fresh Codex branch/worktree from then-current origin/main; recheck overlapping ownership and create a ticket with all parts and the final Learning → skill item.
2. Characterize relevant existing outputs and refusals; add the first failing interface case.
3. Establish the opened view over private index state and move common bounded lookup mechanics without changing their semantics.
4. Migrate Name Frequency and the source.read worker to their owning operations. Keep consumer policy and publication in place.
5. Delete the consumer's private calls, synthetic worker request and duplicate index opening. Verify runtime dependencies and installed behavior where affected.
6. Finish affected verification and independent Standards/Spec/GoF review, update the ticket with real ET completion stamps, then commit/push and create a reviewable PR. Do not merge without named approval.

## Deletion test and cost

The consumer must lose reading-version knowledge and worker-input reconstruction, not receive renamed wrappers around those same chores. Opening, evidence inspection, lookup resolution and traversal must share private state. The worker and the opened view must use one lookup implementation. If both copies remain or Name Frequency still assembles a worker entry, the refactor has failed.

Leverage is modest: one consumer currently reaches through private functions. Locality is the main gain: reading evidence and lookup authentication evolve together, while the full-publication/population policy remains visible in its consumer. Cost: another stateful interface to learn, dependency-fingerprint updates and regression risk around lazy validation and existing loader differences. No throughput or memory improvement is claimed.

## Review status and domain language

**Standards:** read-only source/history inspection in a dedicated worktree at `a01719c43`; this document is outside the repository. Implementation has not begun. Existing runtime ownership and protected shared work remain intact.

**Spec:** both operator decisions are captured: Source Extract owns evidence mechanics; Name Frequency owns domain checks/publication; one opened private view supports evidence inspection followed by bounded iteration. Implementation authorized by the operator on 2026-10-17, together with Relationship Interval ownership.

**GoF:** the private reach-through remains at `name_frequency.py:167` and `:175–176`; independent iteration starts at `:181`. Recent changes to partitioned/derived lookup evidence and Name Frequency are concrete maintenance evidence. Plain module functions and a small state-owning representation are sufficient. Python iteration already supplies the traversal mechanism; no GoF class hierarchy is justified. Guard against facade scope growth by keeping business-policy checks in Name Frequency.

Source Extract and Name Frequency already have precise glossary entries in CONTEXT.md. This design introduces no new business term or hard-to-reverse architectural trade-off, so no glossary edit or ADR is needed.

Recorded 2026-10-17 19:37 ET.
