# Commit the normal Merge Stage atomically

Type: task
Status: claimed
Assignee: Codex
Claimed: 2026-10-23 21:20 ET
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 02, 03

## Question

Can one shared normal MDM caller prepare and atomically commit every merge effect on either storage engine?

## Parts

- [x] Extract one shared Merge Stage preparation; verify joins, new identities and corrections without identity work on PostgreSQL/MySQL, with retained native assessments — 2026-10-24 08:03 ET; three preparation cases per engine and nine native assessment/checkpoint cases pass.
- [x] Complete the normal prepared-store owner command, transactional registry/pin approval, deferred activation and restart qualification on both engines — 2026-10-24 09:35 ET; seven PostgreSQL and six MySQL owner cases pass, including normal CLI, interrupted retry, approval rollback and legacy-write refusal.
- [x] Qualify normal destination preview, assessed intent with actual producing-run publication metadata, held-record natural keys and complete occurrence retention. — 2026-10-24 09:48 ET; 56 normal cases per engine plus the restricted-role admission pack and installed save smoke pass.
- [x] Expand normal-save proof across configured kinds/sources, relationship/detail history boundaries and competing writers; retain native/read-phase regressions and independently installed save smoke. — 2026-10-24 09:48 ET; two kinds and two sources, 56 normal cases per engine, 146/145 retained checks, 15 native PostgreSQL checks and one independently installed save smoke per engine pass.
- [x] Connect shared identity replay, value selection, relationships and detail preparation to the normal Merge Stage save path. — 2026-10-24 09:48 ET; 56 normal cases per engine verify the shared preparation through normal saves.
- [x] Commit source assertions, decisions, identities, current masters, history, detail lists, generation/checkpoints and publication as one admitted destination transaction. — 2026-10-24 09:48 ET; normal late-outbox fault tests verify rollback of all seven business groups; retry succeeds on each engine.
- [x] Validate observed state and registered pins at the destination; refuse stale assessments and competing writers; preserve batch/root-run association and duplicate semantics. — 2026-10-24 09:48 ET; stale/no-identity/concurrent-allocation normal cases and governed admission/refusal tests pass on both engines.
- [x] Prove history boundaries, identity uniqueness, corrections, retirement and unchanged replay with invented configuration. — 2026-10-24 09:48 ET; 56 normal cases per engine, including relationship history and five detail-history states, pass.
- [x] Account for ready/unapplied assessment enforcement, exact assessed effects and root-run duplicate association at the destination; generation alone is insufficient. — 2026-10-24 09:48 ET; restricted-role proposal/intent cases and independent installed assessment/application/replay smoke pass on both engines.
- [x] Preserve relationship/review index envelopes and actual generated review scopes when integrating native index preparation. — 2026-10-24 09:48 ET; normal hierarchy cases verify all three affected identities, with original generated review bodies, on both engines.
- [x] Qualify the minimal prepared-command lifecycle and owner-approved pin capability on both engines, preserving protocol 1–4 fingerprints and direct-request refusal — 2026-10-24 08:03 ET; 87 affected checks per engine pass, plus three shared preparation cases per engine. This qualifies the storage capability, not the normal portable save.
- [ ] Publish the implementation PR, finish final affected reader checks and require every final-head CI check to pass before readiness.
- [x] Learning → skill: update its owning skill on a separate branch/PR, or record none. — 2026-10-24 09:48 ET; mdm-engineering/reference guidance in separate PR #1158; 79 focused checks pass; owner activation, assessed intent/producer metadata, preview, input identity and full-workflow limits recorded.


## Acceptance evidence

Normal merges on both real engines have equivalent durable outcomes; injected failures leave no partial master, history, checkpoint or publication changes.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.

## Initial engineering consult

Lavish feedback: “implement” on the normal atomic Merge Stage. Prerequisites
#1152/#1156 are merged. The current Store still calls PostgreSQL save/assessment
capabilities, and MySQL registry installation deliberately withholds EXECUTE.
Protocol 4 already supplies immutable evidence, indexed projections, generation/
checkpoint enforcement, leases and atomic publication intent. Reuse it and the
existing native preparation; identify any missing admission/assessment operation
before extending the skill adapter. Historical migrations remain immutable.

GoF consult: history #1121, #1148, #1152 and #1156 shows the same transport seam
changing repeatedly. Extract the existing shared preparation from its native
transaction wrapper; use the current Store/Adapter boundary. Avoid a second
merge algorithm or a dialect-specific policy interpreter. The temporary cost
is qualifying both retained native persistence and the replacement path.

## Implementation checkpoint

### Checkpoint 76c1e9a2 (superseded by work in progress below)

Protocol 5 adds destination-owned ready/rejected/applied/superseded proposals,
exact assessed intent checks, observed-generation enforcement and owner-approved
opaque pins. Committed bytes are replayed unchanged for a new observer, preserving
the original producing run. Restricted-role cases cover concurrent admission,
late publication failure with complete rollback, index version refusal, input
publication, pin revocation, migration rerun and protocol 4 upgrade. Historical
protocol fingerprints remain unchanged. The standalone command continues to
expose only the previously qualified public installation protocols; normal
portable write installation is still pending.

Shared preparation is extracted from the existing Merge Stage calculation;
there is no second merge algorithm. Generated review envelopes now retain their
original bodies and index every affected entity as well as affected records.
Explicit review identities must still agree with the envelope. Real PostgreSQL
and MySQL reads verify the generated shape and its indirect entity scope.

Local qualification: 87 affected checks on each engine, three additional shared
preparation cases on each engine, and nine retained native assessment/checkpoint
cases pass. Every invocation finished below five minutes. The current native
wheel was built and selected privately before the review-envelope checks. This
is checkout qualification; installed workflow qualification remains ticket 07.

### Standards

The checkpoint preserves historical migrations, restricted runtime grants,
database-owned generation/fences/atomic writes and configuration-driven policy.
The overlap guard and syntax/name lint pass. Evidence contains counts and
outcomes only. No hosted store or provider was contacted.

### Spec

The helper capability and shared preparation are qualified. Ticket 04 remains
incomplete: owner installation and registered-pin hooks, normal prepared save,
normal assessment application and all-effect history/detail/publication assembly
still need integration and normal-caller proof. Worker/run-control and installed
workflow qualification remain tickets 06 and 07. Portable writes remain gated.

### GoF

The existing Store/Adapter seam remains. `MergeStage._prepare` removes the need
to duplicate affected-record calculation. `Adapter._apply_intent` shares the
same admission RPC between newly prepared commands and exact stored-byte replay.
The latter has two concrete callers; a new strategy hierarchy would add cost
without simplifying these operations. The cost of the extraction is preserving
the retained native save while the replacement path qualifies; its assessment
and checkpoint regression checks pass.

### Normal save integration in progress — 2026-10-24 09:35 ET

The normal owner command now offers an explicit fresh prepared-store install.
PostgreSQL and MySQL select the same shared Merge Stage preparation from the
installed storage protocol. Owner registry activation and approved references
become visible atomically before runtime execution is granted. A populated
native PostgreSQL store is refused pending a qualified data migration.

Normal caller coverage passed 56 cases per engine, spanning two invented kinds,
two source priorities, identifier and configured name matching in both arrival
orders, concurrent first identity allocation, no-identity stale retries,
relationships, hierarchy review scope, exact numeric detail history, quarantine,
corrections, retirement, assessments, rollback, occurrence retention and replay.
The retained regression pack passes 146 PostgreSQL and 145 MySQL checks. Each
invocation finished below five minutes; these are checkout API results.

Destination preview exercises the same storage validation and write assembly,
then rolls back every business effect. Assessed intent excludes the observing
run while publication inserts the actual producing run, preserving exact byte
hashes and original-producer batch association. Natural source revision and
held-record references retain their immutable original bodies; occurrences
remain individually retrievable.

Final review reuses the validated publication-floor reader and bulk identity
probes rather than trusting raw reference bodies or probing once per kind.
Final affected reruns and an independent committed five-wheel save/assessment/
replay smoke are in progress. This checkpoint is incomplete. Public/operator
reads are ticket 05; external worker authority, per-run source-mapping freezes,
publication recovery and run observation remain ticket 06. They are explicitly
refused where their normal Store methods are called, rather than reported as
success. Full installed workflow evidence remains ticket 07. Historical SQL
migrations and native rollback behavior are retained.

### Independently installed save qualified — 2026-10-24 09:48 ET

Both engines pass the committed five-wheel installation smoke from revision
73123361, outside the checkout in isolated Python. It checks packaged adapter
and native-library provenance, normal owner installation and approved source
registration, rollback-only preview, normal assessment and application,
80-digit-plus exact integer readback, and duplicate replay with unchanged
business counts. PostgreSQL passes in 18.06 seconds; MySQL in 24.88 seconds.
Final normal-save reruns pass all 56 cases per engine in bounded groups.
Fifteen retained native PostgreSQL assessment/checkpoint checks pass.

Two initial installation test runs hit the 280-second deadline while sharing
the native distribution-cache build lock. The concurrently loaded second-kind
reruns also timed out. Their disposable containers were stopped. A serialized
five-wheel build finished in 82.40 seconds; the installed proofs and normal
reruns then passed. An attempted installed test using a saved local test-instance
connection was refused before execution; the successful proofs use fresh
isolated databases. Timeouts and connection refusal are not counted as passes.

### Standards — normal save review

Fresh dedicated branch and worktree; no historical SQL is edited. Protocol
1–4 fingerprints and restricted-role enforcement are retained. Evidence uses
invented inputs and counts/outcomes; no provider or hosted target is contacted.
Overlap and syntax/name lint pass. SQL Server full workflow stays deferred;
its normal migration refusal is checked once rather than repeated per fixture.

### Spec — normal save review

The normal Store/Merge Stage save and independent installed save smoke pass
on PostgreSQL and MySQL. The explicit fresh prepared-store owner command
refuses populated native conversion without qualified migration. This work
does not establish operator/context/Silver reads (05), configured worker
external authority, source-mapping run freeze, publication recovery (06),
full installed matrix (07), or PostgreSQL routine retirement (08).

### GoF — normal save review

The existing Adapter boundary carries opaque prepared effects; the shared
Merge Stage preparation remains the single policy interpretation. Evidence
from #1121, #1152 and #1156 supports this repeatedly changing transport seam.
The preparation extraction removes duplicate calculation; publication-floor
validation and bulk identity reads are reused at that seam. A strategy/class
hierarchy would add dispatch and maintenance without removing an observed
variation. Retaining the native writer during qualification costs dual-path
regression checks; those checks pass. No further pattern refactor is justified.
