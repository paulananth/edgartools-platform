# Connect master reads and operator commands

Type: task
Status: claimed
Assignee: Codex
Claimed: 2026-10-24 09:55 ET
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: none; prerequisite 04 merged in #1159

## Question

Can installed consumers and operators use normal engine-selected MDM read and inspection paths?

## Parts

- [x] Connect and qualify actual Silver delivery and refresh against normal MDM saves on two configured kinds and both engines — 2026-10-24 18:24 ET; two real Silver integration cases per engine pass, including later mastery, merge, reversal and unchanged refresh.
- [ ] Finish current/history/detail/relationship/context reads and independently installed master-identifier lookup used by Silver.
- [ ] Connect counts, connectivity, health, inspection and supported publication commands to selected-engine storage; preserve authorization and bounded exact-key plans.
- [ ] Verify original JSON, large numbers, Unicode and opaque identifiers survive transport; keep errors and public evidence free of source values.
- [x] Qualify existing applied-event recording time and generation-pinned pages without a storage extension — 2026-10-24 20:04 ET; recording/business-time boundaries and metadata key plans pass on both engines; all 13 supported protocol/engine migration fingerprint sets match current main.
- [ ] Qualify the normal installed consumer/context and actual Silver-facing lookup on both engines, with original provenance, aliases, historical detail boundaries and bounded plans.
- [x] Qualify current/historical entity, original producer, alias, profile, detail, plan, unknown-key and inspection cases locally for two configured kinds — 2026-10-24 19:19 ET; 18 cases per engine passed before the recording-time join, with current/producer and key-plan checks rerun after that join.
- [x] Qualify indexed generation-pinned snapshot paging across later merges and future identities — 2026-10-24 19:19 ET; two cases per engine pass. Pages use stable storage-key order and original IDs as cursors; no new schema or ID length cap.
- [x] Prove 405-field original provenance without per-field query transport — 2026-10-24 19:19 ET; one case per engine passes with fewer than 30 read queries. The second configured kind and latest recording-time join remain to qualify.
- [x] Connect current Context entity answers and populated related links through the actual read-only CLI — 2026-10-24 19:30 ET; four cases per engine pass across both configured kinds, plus 13 Context units and six retained native PostgreSQL cases. The later single-snapshot change has a passing PostgreSQL concurrency case per kind; MySQL observation is pending.
- [x] Qualify historical Context links and full relationship CLI answers, with original source evidence — 2026-10-24 20:04 ET; two cases per engine pass for both configured kinds, before and after an endpoint change.
- [x] Qualify Context identifier and cross-reference lookup, waiting carriers, ambiguity and canonical redirects — 2026-10-24 20:04 ET; two cases per engine pass through existing indexed references and shared Rust normalization.
- [x] Qualify single-snapshot Context under a concurrent normal save — 2026-10-24 20:04 ET; two cases per engine pass. The delayed MySQL result was observed terminal at 19:58 ET.
- [x] Refuse uninstalled prepared-store name search explicitly — 2026-10-24 20:04 ET; two cases per engine return a bounded semantic error and supported lookup commands. This qualifies refusal, not name search.
- [ ] Finish prepared master-name search with indexed completeness and a governed populated rebuild; current native-only search is an explicit capability gap.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

## Acceptance evidence

Normal installed reads and commands work on both engines, including the real Silver-facing lookup; helper callbacks alone do not qualify the path.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.

## Initial consult — 2026-10-24 09:55 ET

The fresh reader branch starts from current origin/main and carries prerequisite
04 commits by fast-forward; PR #1159 is still in CI, not merged. It changes no
runtime on this branch yet. Existing native readers remain the rollback path.

GoF review of consumer.py, Context and Silver MdmIds plus their histories shows
a shared transport gap, not a new merge algorithm. Keep their public contracts,
use typed selected-engine queries and reuse validated RecordReader references.
The portable path must handle every configured kind uniformly. Preserve native
PostgreSQL behavior until retirement is separately qualified.

Inspection found that the prepared batch model has generation, producer and
intent, but no destination recording timestamp. Context currently distinguishes
business --as-of from recording --as-at and returns original recorded_at.
Investigate that behavior on real prepared stores before choosing the smallest
storage extension; caller business time must not stand in for server recording
time. Current history keys support exact object/generation reads, but pages
ordered by original opaque ids and master-name search need demonstrated indexed
plans. Keep these explicit; a full-table Python filter is not an implementation.

Task 05 remains incomplete. No Context ownership is assumed: reconcile its
standing Claude ownership and live overlap before editing that command module.
Other consumer and Silver read work can progress independently.

## Real Silver lookup checkpoint — 2026-10-24 18:24 ET

The branch is rebased onto current main 71b3e776; prerequisites #1158/#1159
are merged. `MdmIds` now uses the existing RecordReader/Adapter boundary for
prepared storage and retains the native SQL path for legacy PostgreSQL.
It verifies exact source-record keys, immutable reading provenance, kind and
current master identity; canonical IDs come from the stored master, without
replaying matching. Pointer, reading and master share a repeatable-read
snapshot. A concurrent normal merge between those probes returns the old
coherent result, followed by the new result on the next lookup.

Local results: 14 PostgreSQL cases and 14 MySQL cases are verified across two
configured kinds, including real Silver delivery/refresh, waiting records,
merges/reversals, long Unicode keys, and 405-record grouped reads. The final four MySQL second-kind cases were observed passing at 18:51 ET,
after the required observation interval. Two retained native PostgreSQL Silver integration cases
pass. Actual query plans verify all pointer, immutable evidence and master
probes used by the 405-record lookup; statement counts prove grouped transport.
These are checkout proofs, not the independent installed workflow matrix.

The first Silver fixture failure was reuse of a dictionary already enriched
by `land`; replay now reconstructs original delivery rows. The stored-result,
master-change and unchanged-refresh assertions remain intact. No runtime
exception was hidden or storage assertion relaxed.

### Standards

Own branch/worktree, no migrations changed, existing storage index queries
reused, no source/kind branches added to the engine. Evidence contains invented
values and counts/outcomes. Overlap guard, syntax/name lint and whitespace pass.

### Spec

The real Silver-facing lookup now works on both prepared stores and retains
native PostgreSQL behavior. Consumer/history/context, inspection and installed
qualification remain open; recording-time and ordered-page storage gaps still
require investigation. Ticket 05 remains incomplete.

### GoF

Reuse the current Adapter and RecordReader seam. The added operation transports
stored identity pointers and validates provenance; it introduces no second
matching algorithm or strategy hierarchy. Its cost is several grouped probes,
held in one snapshot instead of the native single SQL join. The concurrency
and 405-record checks qualify that specific cost and consistency boundary.


## Read integration checkpoint — 2026-10-24 19:07 ET

Current, historical, producer, alias, profile, detail, indexed-plan, unknown-key
and inspection cases pass for both invented kinds on both engines: 18 cases
per engine. The delayed MySQL current-read handle was observed terminal with
two passes at 19:06 ET. Bulk provenance and Context integration remain open;
no independent installed-reader proof is claimed.

The initial recording-time concern was too broad: the batch table has no
recording-time column, but protocol 5 already writes a database-owned
`proposal_event.occurred` for an applied proposal in the admission transaction.
That existing authority must be qualified before considering a new storage
extension. Reading the SQL establishes its presence, not its behavior or a
bounded recording-time query. No new timestamp table or protocol migration
has been introduced. The Context reproduction still fails through the current
normal command, so that application integration remains incomplete. The operator explicitly assigned `edgar_warehouse/context.py` to Codex for
this ticket; its standing Claude ownership is resolved for this
scope.


## Ownership ruling — 2026-10-24 19:11 ET

The operator answered “Assign context.py to Codex.” Codex owns the Context
integration in this ticket; other runtimes' unrelated work remains protected.


## Recording and paging checkpoint — 2026-10-24 19:19 ET

Original producer and destination recording microseconds now come from the
existing applied proposal event. Grouped origin reads verify its batch and
observer bytes, reject missing or ambiguous origins, and retain immutable
input hashes. Indexed metadata plans pass on both engines; producer cases
for both configured kinds preserve the entire original origin after replay
by a different observer and after a new unchanged batch. No migration,
clock substitution or protocol fingerprint change was needed.

Generation-pinned pages use existing primary-key ranges, then exact
historical seeks. The cursor is still the last original object ID; ordering
is by its stable storage hash on both prepared engines, without imposing a
collation or length on opaque IDs. This differs from the retained native
PostgreSQL path's lexical ID order; consumers must follow `next_after`.
Historical content, aliases, future-object exclusion and page hashes pass
for both configured kinds. Relationship/review populated pages, late-page
row counts and independent installation are still open.

The page fixture initially tried to allocate two identities at the same
publication floor; the destination correctly refused it. Its second
publication now advances that floor. The runtime guard is unchanged.

Remaining tracked proof handles: applied-event-only cases 70483 and 74313
started at 19:08:54 ET; observe no earlier than 19:38:54 ET under the
30-minute rule. They predate the origin-query extension, so their results
will not qualify the newer query. The earlier bulk handles are terminal
and passed. The Lavish poll is attached as process handle 40416.


## Current Context checkpoint — 2026-10-24 19:30 ET

The normal read-only Context CLI resolves current master IDs through the
portable consumer, reads original applied-event time, validates current
source-reading references, and reads related projections through existing
incoming/outgoing indexes. Two configured kinds pass empty and populated-link
answers on both engines. Retired relationships are excluded; the retained
link target is verified. Restricted-role CLI output agrees with the direct
Context result. Context's master, provenance, sources and links now share a
repeatable-read transaction; PostgreSQL concurrent-save cases pass for both
kinds. The matching MySQL handle 56771 started at 19:28:29 ET; observe no
earlier than 19:58:29 ET, without restarting it.

The first CLI fixture exposed missing catalog metadata: its invented kind
was registered with the engine but absent from Context definitions, which
control command routing. The fixture now configures that definition before
calling the CLI. No routing guard was bypassed. The populated-link fixture
uses the existing normal relationship-save proof directly; Silver's separate
fixture requires a different binding state and is not reused for this case.

Time selection, historical adjacency, identifier/cross-reference lookup,
name search, full relationship commands and independent installed proof
remain open. The original historical Context reproducer still fails; it is
not skipped, relaxed or counted as a pass. Ticket 05 is incomplete.


## Reader checkpoint — 2026-10-24 20:04 ET

The original historical Context reproduction now passes for both configured
kinds on both engines. Recording-time and business-time boundaries, a time
before any saved state, exact 401-digit integers, source/reference lookup,
ambiguous references, held records, canonical redirects and full historical
relationship CLI answers pass. Normal Context answers use one read snapshot;
the MySQL concurrent-save result is terminal and passing, as is PostgreSQL.
All 11 retained native PostgreSQL Context cases and 13 Context units pass.

Metadata reads page backwards through bounded generation keys; the first
eligible generation preserves the existing max-generation semantics without
assuming business timestamps are monotonic. PostgreSQL uses exact generation
probes; MySQL uses its generation index. Applied-event provenance is checked
on every page. Business-time extraction parses original bytes in Python on
MySQL: its native JSON parser rejected an otherwise valid 401-digit integer
(error 3141). PostgreSQL extracts JSON text without converting all numbers to
JSONB. Recording-time lookup stays thin. MySQL business-time lookup transfers
retained assessment bytes in bounded pages; retrospective lookup can walk
multiple pages. Large-store latency is not claimed qualified by these cases.

Historical links need no new adjacency table: normal relationship IDs include
their endpoints, and retirement retains their endpoint references and current
marker. Existing endpoint indexes therefore address historical versions;
later-created links have no earlier version. The endpoint-change fixture
proves that old and current targets differ correctly, with original evidence.

Prepared-store name search has no installed master-name index or governed
populated rebuild. It now refuses explicitly rather than returning an empty
answer from legacy PostgreSQL storage. Completing that capability remains on
this ticket. Force publication and worker observations remain allocated to
06. No full installed-reader or installed-workflow pass is claimed.

The current/producer repeat selector also selected Context current/concurrency
cases because pytest matches substrings. Those tracked jobs started at
20:01:42 ET: PostgreSQL handle 46255, MySQL handle 80143. Observe no earlier
than 20:31:42 ET; do not restart them. Other proof handles are terminal.

### Standards

Own branch/worktree and explicitly assigned Context ownership; overlap guard
passes. No model, SQL migration, grant, business rule, source-specific branch
or entity-specific branch was introduced. All 13 supported migration
fingerprint sets match current main. Changed modules compile, undefined-name
lint and whitespace checks pass. Public evidence is counts/outcomes only.

### Spec

Normal current/historical master and Context reads, original provenance, real
Silver lookup and operator inspection have local engine proof. Name search,
independent installation, remaining populated page/transport cases and worker
publication are still open. Passing local reads does not authorize activation
or close ticket 05 or installed qualification 07.

### GoF

The existing Adapter/RecordReader/ContractReader boundary remains. Generic
storage metadata and key queries stay in the adapter; configured identifier
normalization reuses the shared Rust primitive. Context formats existing
stored facts and does not run matching. No new strategy hierarchy, duplicate
merge algorithm or second timestamp authority is justified. The cost of the
portable seam is grouped key probes and bounded metadata pages; concurrency,
large provenance and actual index plans cover that boundary, while deep
retrospective latency and installed completeness remain explicit limits.
