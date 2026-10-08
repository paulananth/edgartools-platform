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
- [ ] Implement generic bounded reduction/composition over authenticated complete source streams; preserve unique holders, duplicate-LEI last timestamp, capped samples, counts and exact evidence identity.
- [ ] Express complete source census construction in bundled Rules, with immutable source/context receipts and separate worker verification.
- [ ] Qualify actual captured records and deliberate faults before full scans; measure runtime and setup separately before selecting full-scan concurrency.
- [ ] Construct and compare the complete pinned SEC/GLEIF census through valid original-source EOF; preserve cascade decisions and source population evidence.
- [ ] Verify installed empty restricted PostgreSQL16 population (6,414 Company / 3,052 CIK+LEI), unchanged replay and recovery; do not substitute the two-Company fixture.
- [ ] Replace active census/preparation consumers only when their complete provenance, pagination, classification, catalog and recovery contracts are proven.
- [ ] Retire obsolete production census/construction code after no active caller remains; retain independent test-only oracles until equivalent guarantees exist.
- [ ] Update self-contained bundled skill instructions, examples and requirements audit; full affected/native/CI gates, independent reviews and reviewable PR.
- [ ] Parent goal still requires remaining Company/GLEIF runtime, complete adapter record mapping and configured capture retirement; preserve sec_client until provider.capture is qualified.

## Evidence and design

Base: bbc3daa3 (#867, CI 37770383925 passed). Main remains 862a1e66.
Dedicated branch/worktree: codex/whole-source-census-20261008.
Current combiner permits 100,000 rows, 64 MiB aggregate input and only
collect/first/last/one modes. It cannot currently construct the whole GLEIF
census. Native streaming projection uses empty lookup sets, although eager
reads already accept indexed sets. Context is scalar-only and limited to
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
