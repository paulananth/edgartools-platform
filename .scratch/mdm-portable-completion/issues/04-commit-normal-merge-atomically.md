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
- [ ] Connect shared identity replay, value selection, relationships and detail preparation to the normal Merge Stage save path.
- [ ] Commit source assertions, decisions, identities, current masters, history, detail lists, generation/checkpoints and publication as one admitted destination transaction.
- [ ] Validate observed state and registered pins at the destination; refuse stale assessments and competing writers; preserve batch/root-run association and duplicate semantics.
- [ ] Prove history boundaries, identity uniqueness, corrections, retirement and unchanged replay with invented configuration.
- [ ] Account for ready/unapplied assessment enforcement, exact assessed effects and root-run duplicate association at the destination; generation alone is insufficient.
- [ ] Preserve relationship/review index envelopes and actual generated review scopes when integrating native index preparation.
- [x] Qualify the minimal prepared-command lifecycle and owner-approved pin capability on both engines, preserving protocol 1–4 fingerprints and direct-request refusal — 2026-10-24 08:03 ET; 87 affected checks per engine pass, plus three shared preparation cases per engine. This qualifies the storage capability, not the normal portable save.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

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
