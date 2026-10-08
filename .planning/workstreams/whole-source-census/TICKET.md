# Whole-source configured census construction

Parent goal: self-sustaining bundled skills and Rules creator, configured
parsing/MDM orchestration, custom parsing only after an approved demonstrated
need, and complete retirement of executable old parsers.

The prior census extraction PR #867 proves a bounded caller slice. This
work must construct a complete census from authenticated source populations,
preserve counts/cascade/refusal semantics, and qualify the active replacement.
Neither an indexed-membership primitive nor a sampled construction alone
completes this ticket or the parent goal.

- [x] Inspect live refs, dedicated Codex tree, guarded paths, active census/preparation callers and source archive size (927,550,946 bytes; 1,808,797,696 free). Main 862a1e66, base #867 bbc3daa3, #866/#867 open and CI green. 2026-10-08 07:56 ET
- [x] Review engine/combiner history with GoF reviewer and new-worker design with GoF selector: preserve interpreter/functions; borrowed immutable projection scope validates indexed sets once instead of rescanning all keys per record. 2026-10-08 07:56 ET
- [x] Add bounded declared member expressions and indexed JSON streaming projection; exact keys, missing/extra sets, raw duplicates/generator prefix, Unicode byte bounds, lazy branches, empty streams, frozen values, EOF and callback failures tested. Full native suite 145 passed; affected Python tests 111 passed in 18.80s. 2026-10-08 07:56 ET
- [ ] Build native configured census projections preserving category/LEI/key/timestamp/other-name read order and cascade eligibility/quality.
  - [x] Implement ordered native name projection and explicit generic empty iteration; 146 native tests and 134 affected Python tests passed (51.66s); canonical Rules loader and transform drift invariant included. 2026-10-08 18:11 ET
  - [x] Compare 1,000 hash-authenticated captured GLEIF prefix records and five trials against independent extraction and current configured callback baselines; exact rows agree. See captured-name-projection.json; original-source EOF and cascade remain unqualified. 2026-10-08 18:11 ET
  - [ ] Add GENERAL cascade field/quality projection and global address-frequency inputs before replacing active construction.
- [ ] Implement generic bounded reduction/composition over authenticated complete source streams; preserve unique holders, duplicate-LEI last timestamp, capped samples, counts and exact evidence identity.
  - [x] Add incremental authenticated inline/partition traversal with aggregate limits, original evidence, EOF accounting, empty schemas and isolated private metadata; 151 targeted/genericity tests passed in 17.26s, including consumer-mutation and >32 MiB loader-compatibility regressions. 2026-10-08 18:45 ET
  - [x] Qualify actual captured-prefix worker output through exhausted incremental traversal; 1,000 records agree with the independent oracle, retry/replay pass, and runtime pins are unchanged. Final broader gate: 279 passed in 37.39s. 2026-10-08 18:47 ET
  - [ ] Measure complete-index snapshot copying at large partition counts before full-source reduction; preserve isolation if optimizing metadata sharing.
  - [ ] Implement declared reduction state/output limits, holder-set subtraction, counts and last occurrence semantics; incremental traversal alone does not implement reduction.
- [ ] Express complete source census construction in bundled Rules, with immutable source/context receipts and separate worker verification.
  - [x] Implement version-3 source.read input/context/lookup receipts, raw set bounds before source access, output evidence and consumer identity gate; 207 affected tests passed in 41.99s. 2026-10-08 18:27 ET
  - [x] Real configured census worker execute/retry/replay verification agrees with independent captured-prefix oracle on 1,000 records; worker_proof records receipt hashes and table counts. Separate-process and original-source EOF qualification remain false. 2026-10-08 18:27 ET
  - [ ] Derive wanted population and publication count from complete authenticated upstream inputs, preserving original source population identity; installed independent-process proof remains required.
- [ ] Qualify actual captured records and deliberate faults before full scans; measure runtime and setup separately before selecting full-scan concurrency.
- [ ] Construct and compare the complete pinned SEC/GLEIF census through valid original-source EOF; preserve cascade decisions and source population evidence.
- [ ] Verify installed empty restricted PostgreSQL16 population (6,414 Company / 3,052 CIK+LEI), unchanged replay and recovery; do not substitute the two-Company fixture.
- [ ] Replace active census/preparation consumers only when their complete provenance, pagination, classification, catalog and recovery contracts are proven.
- [ ] Retire obsolete production census/construction code after no active caller remains; retain independent test-only oracles until equivalent guarantees exist.
- [ ] Update self-contained bundled skill instructions, examples and requirements audit; full affected/native/CI gates, independent reviews and reviewable PR.
  - [x] Document member grammar, declared set bounds, worker version-3 receipts, raw/UTF-8 validation, immutable scope and qualified combine identity route; 91 affected/genericity checks passed in 3.78s. 2026-10-08 18:34 ET
  - [ ] Qualify installed separate-process worker/verifier and full source construction before recording whole-source retirement.
- [ ] Parent goal still requires remaining Company/GLEIF runtime, complete adapter record mapping and configured capture retirement; preserve sec_client until provider.capture is qualified.

## Evidence and design

Original base: bbc3daa3 (#867, CI 37770383925 passed). At ticket opening,
main was 862a1e66; synchronization onto 40741eed is recorded below.
Dedicated branch/worktree: codex/whole-source-census-20261008.
Current combiner permits 100,000 rows, 64 MiB aggregate input and only
collect/first/last/one modes. It cannot currently construct the whole GLEIF
census. At base #867 native streaming projection used empty lookup sets, although
eager reads accepted indexed sets; the indexed-membership prerequisite above
replaces that limit. Context is scalar-only and limited to
32 KiB; embedding 43,245 census keys in context is not a supported solution.
Frozen inline references cap each table at 10,000 keyed rows.

Preserve the existing interpreter and plain functions. Extending existing
indexed read sets and configured reductions addresses demonstrated input
size and callback costs. No provider-specific loader or new class hierarchy
is justified. GoF history shows repeated configured-reader extensions and
source-combination changes; maintain bounded reusable operators rather than
coupling the worker to Company or GLEIF. Iterator behavior uses the existing
language streaming callbacks, not a new iterator class. Strategy classes
would add state/dispatch without an actual family of implementations.

Local qualification only. No SEC requests, source activation or deployment.
Full scans previously took tens of minutes; announce the measured estimate
before starting a new full scan and report elapsed time for steps over ten
minutes. The pinned captures and Golden Copy are already local.

## Current evidence and remaining construction work

All seven cascade passes P1-P7 are active in the live policy. A replacement
must preserve GENERAL/quality eligibility, global address-frequency counts,
name candidate scope and each ordered pass's assignments. Dropping cascade
or qualifying name counts alone would change the required result.

The native implementation adds declared lookup_sets bounds and member
expressions. LookupProjection borrows immutable sets after one validation;
Python ingestion bounds raw values before deduplication, then freezes them
before any stream reads. Existing undeclared eager in_lookup checks retain
their behavior. Context remains scalar-only; no large-scope context workaround
or source-specific callback is introduced.

The initial lazy-branch regression used a boolean const, which the established
grammar returns as a scalar. Corrected the test to a typed test/equal condition;
no existing const semantics were changed. Native/Python gates passed afterward.

Whole-source projections, generic reduction/composition, capture authentication,
complete original-source EOF, cascade parity, installed full population and
active-caller retirement above remain unchecked. This is implementation
progress inside that full ticket, not a completed smaller substitute.


## Ordered name projection checkpoint

`census-names-stream.yaml` uses the frozen wanted lookup, ordered legal/other/
transliterated tables, and lazy eligibility. It reads category, LEI and legal
key before a wanted timestamp, then other names. `each.empty: {}` skips an
excluded record without relying on a supposedly absent captured path.
Other-name rows retain legal-name aliases; the complete reducer must subtract
final legal-holder sets, preserving duplicate-LEI last timestamp semantics.
No active caller has been replaced by this checkpoint.

Captured qualification used the hash-pinned original archive's first 1,000
records and a synthetic wanted population of 990 keys. Valid EOF is proved
only for the repackaged sample. Five-trial medians: native framing/projection
1.686500538s, current configured callback 16.663666274s, decoded Python oracle
extraction 0.151362968s; setup/authentication 17.146892116s. Timings are visibly
variable and the decoded oracle omits framing/decoding. They do not establish
whole-source runtime, cascade cost, memory bounds or a universal Rust speedup.

Review caught YAML aliases from generic serialization, incompatible with the
supported Rules file loader. Rewrote with files.dumps, tested with files.load,
and extended the canonical normalizer-transform equality invariant. The
initial refusal-order test assumed path details in an error; corrected it to
assert stable value_type before objects_shape after restoring Registration.
The independent historical oracle still refuses the same first malformed read.

At the initial projection checkpoint, lookup receipts were the next integration
gap. The receipt integration below closes that transport gap. source_readings.load
still materializes partitions within a fixed consumer budget. Full reduction must consume authenticated
partitions incrementally rather than enlarge those bounds or silently omit
cascade/global addresses. Worker/verifier must reject provisional source prefixes
and preserve immutable source population identity before any publication.

Current adapter inspection: configured mappings already project both fields
and matching through source_mapping; do not describe matching as universally
custom. Classification, key/provenance/scope/link construction and fallback
branches still require active-caller inventory and complete retirement proof.

## Lookup receipt integration — 2026-10-08 18:27 ET

The worker now authenticates version-3 input/context/lookups receipts and a
version-1 lookup document (`input`, `sets`). Raw duplicate counts, exact text,
per-key/aggregate UTF-8 bounds and exact declared set names refuse before source
snapshots open. Native JSON projection freezes the accepted scope once. XML
indexed streaming is explicitly unsupported; no implicit fallback is added.
Lookup evidence survives partition output and normalization. Existing consumers
must explicitly bind that evidence into output identity: direct mdm.prepare
refuses it, while source.combine's full reading receipt participates in the
hashed combined scope. Identical rows under distinct lookup receipts produce
distinct MDM publications through that tested route.

The recipe now declares ZIP stream framing, output/spool limits and a pinned
publication_count context. Count agreement at EOF proves agreement with a
supplied authenticated receipt; it does not independently derive that receipt.
Captured worker verification runs in the qualification process, so it is not
an installed/separate-process qualification. Full population is still pending.

Live merge check: #866 merged 4392159e, #867 merged dec6c867, #874 generic skill
methods merged 0899b238, #875 progress audit merged ec2f45ab, #876 generic
READING/COMBINING/control skill methods merged 40741eed. origin/main refreshed
to 40741eed. The progress audit retains the original 6,414/3,052 installed gate.
Synchronization completed 2026-10-08 18:34 ET: checkpoint 70c1c410 preserved, then the
two owned commits rebased onto 40741eed as cf418c98 and 34b7dacc. The sole
READING.md conflict preserves generic main wording and the empty iterator
grammar; 265 affected/genericity checks passed in 71.12s. Main's unrelated
dirty checkout remains untouched.

Synchronization and checkpoint publication are recovery anchors only. This
ticket remains incomplete; no active census caller or remaining parser was
deleted, and no rules were activated or deployed.

## Incremental traversal checkpoint — 2026-10-08 18:47 ET

`iter_load` consumes authenticated partitions without retaining every projected
row. Legacy `load` uses the same validation and keeps its original caller byte
limit. New incremental traversal caps its index at 32 MiB, accounts aggregate
bytes/rows, validates complete source ranges before content, and yields empty
schemas for zero records. Returned evidence cannot mutate private future receipt
selection. Later content corruption still invalidates a private prefix; a
future reducer must exhaust before publication. This adds traversal, not the
remaining aggregation or active-caller replacement.

Fresh captured report: 1,000 records, 990 synthetic wanted keys, exact table
counts 998/1/43; worker execute/verify/retry/incremental consumption 3.397055667s,
setup 8.606674207s. Five-trial native median 0.743046181s, configured callback
median 9.657779893s, decoded oracle median 0.073478324s. These replace the
report file's prior runtime pins and timings; the historical checkpoint above
remains dated evidence. Original EOF, cascade and installed population flags
remain false. Native sources are unchanged since the 146-check native gate.
