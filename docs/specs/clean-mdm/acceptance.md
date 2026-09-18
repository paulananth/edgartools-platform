# Local acceptance, consumer migration, and target qualification

Status: required acceptance matrix. The [evidence report](evidence.md) records
passing local foundation/core checks and the remaining integration gates.
No hosted qualification or cutover gate has passed.

## Local PostgreSQL foundation

Use a disposable PostgreSQL 16 instance bound only to loopback, with a unique
database/container owned by this workstream. On this Mac, Docker uses Colima.
Use `uv` with the repository's locked dependencies and applicable MDM extras.
The acceptance runner must fail on unavailable PostgreSQL, wrong major version,
unapplied migrations or insufficient permissions. No prerequisite skips and
no SQLite substitution. Record server version, image digest, migration
checksums, role grants, source/policy fixture digests and code commit.

Exercise real ordered SQL migrations through the runtime migration mechanism;
`metadata.create_all()` is not migration evidence. Start from an empty isolated
target and retain the legacy schema/database separately. Repeated migration
application is verified and altered historical checksums rejected. Runtime
credentials are separate from migration-owner credentials. Test permissions
with the actual application role, including inherited membership and future
objects/default privileges.

Local acceptance has no Snowflake credentials, no AWS calls and no live source
dependency. Pin representative, license-appropriate fixture bundles with
schema version, publication identity, manifest and hashes. Prefer synthetic
fixtures that express source semantics over copied personal production data.
Inject source readers and publication sinks; local export/graph sinks must
enforce contract, ordering, idempotency and receipts, not just return success.
They do not constitute live Snowflake/graph qualification.

## Required fixtures and executable assertions

| Acceptance gate | Representative test and required proof |
| --- | --- |
| Identity/profile separation | Company with Adviser + Audit Firm profiles; Person with Adviser profile; same spelling across kinds cannot merge; 13F manager does not acquire regulated Adviser status |
| Fund and issuer semantics | Incorporated fund vs contractual/umbrella/subfund; Security share class remains separate; accepted government issuer and deferred unsupported issuer |
| Deterministic result | Same evidence, policies, steward decisions and retained identity registry replayed with record permutations, batch sizes, duplicate deliveries and worker scheduling; equal identities, fields, aliases, edge sets and business hashes. Registry-preserving replay follows accepted Q3. |
| Automatic binding qualification | Each enabled kind/rule family meets the accepted 99.9% precision target using a one-sided 95% lower confidence bound on independently labeled representative held-out decisions; zero hard-veto violations in adversarial fixtures; measured recall/review volume; under-sampled rules remain review-only. Actual score cutoffs and corpus evidence are still outstanding. |
| Conflict safety | Exact ID ambiguity, same-name homonyms, incompatible kinds, authoritative-ID disagreement, and three-record transitive bridge produce recorded conflicts without consolidation |
| Field provenance | Equal-ranked disagreement has a stable winner; coherent field groups retain one source claim; source assertion, policy digest, origin run and losing evidence remain queryable; an override without expiry persists until revoked; explicit expiry and contradictory source updates follow approved policy |
| Corrections/deletion | Old correction arriving late; absent vs null vs clear vs retract; complete snapshot retirement vs partial snapshot/delta absence; source withdrawal allows only eligible fallback |
| Atomicity and lost acknowledgement | Fault before transaction, after each business write, before commit, immediately after commit, and before receipt; compare state/checkpoint/intent and verify no duplicate business effects |
| Concurrency | Two DB sessions competing for same subject/checkpoint, expired worker fence, and overlapping merge components; stale transaction cannot commit |
| Reversal | Wrong merge followed by valid field correction, relationship and dependent merge; preview/replay restores partitions without losing later evidence; ambiguous facts are deferred; dependent merges require review before reversal activation; unrelated processing continues; Match Exclusion prevents replay from recreating the rejected merge |
| Hierarchies and dates | Accounting-parent cycle during overlapping intervals; non-overlapping historical edges; conflicting direct parents, legitimate multiple ownership stakes, invalid intervals and self-links; reported/calculated ultimate parents stay separate |
| Publication failure | Export failure, graph failure, reordered generations, external success with lost receipt, lease expiry; retries converge and Bookkeeping remains incomplete until all required receipts verify |
| Permission enforcement | Runtime cannot DDL, truncate, alter activated policies, or update/delete assertions/journal; approved merge/publication operations work; inherited grants cannot bypass protection |
| Entrypoint integration | Every existing mastering, derivation, seed, steward, repair and reconciliation route writes through Merge Stage; bounded limits do not claim complete scope |
| API/export/graph contract | Golden fixtures for shared IDs/profiles/provenance/aliases, reported vs derived edges, endpoint kinds and dates; exact keys/property hashes and required consumer completeness |

One-time rebuild, backfill and reversal tools require `--limit` or an equivalent
bounded-sample mode and resumable batch cursors from their first implementation.
Dry-run alone is not a bounded sample. A sample cannot satisfy whole-population
or complete-snapshot gates.

## Consumer contract proposal

Define a new explicit major version for identities, profile memberships,
identifier history, selected fields/provenance, relationships, aliases and
retirements. Each envelope includes schema version, generation, origin run,
policy digest and business-content hash. Profile IDs identify registrations;
they do not masquerade as additional Company/Person identities.

API responses expose canonical and requested/alias ID, identity kind, active
profiles and dates, field attribution, and links to conflicting evidence.
Historical/as-of reads must say which valid-time and projection watermark they
represent. Export separates reported relationships from calculated edges;
calculated edges reference their algorithm and input path/watermark. Graph
keeps one node per shared identity and explicit governed profiles rather than
blindly relabeling old Adviser nodes.

Before enabling outputs, inventory actual API/export/graph consumers, pin each
to its contract version and require their compatibility tests. Old consumers
remain on the retained old MDM unless an explicit read-only compatibility
projection is proven. Publish old-ID → new-ID/profile mappings with ambiguous
cases unresolved. Never manufacture synthetic duplicate identities just to
make a legacy row count match.

Consumer completeness accounts for all required source records: accepted,
unchanged, validly retired, explicitly out of scope, or unresolved. Unresolved
required records block activation. Counts alone do not prove parity: compare
identity mappings, fields and winners, profile intervals, relationships,
endpoints, aliases and source coverage at the same watermark.

## Snowflake Postgres qualification

Only after local acceptance, provision an isolated target through the existing
approved AWS/Snowflake operator boundary. Install the same reviewed migration
set and replay the same fixture suite with the target application role.
Capture target PostgreSQL version, supported SQL/features, effective grants,
transactions/locks, UTC/time behavior, and representative performance. Local
success does not prove hosted role or compatibility behavior.

Build an approved source manifest with exact publication/member hashes and
source positions, code/image digest, registry/policy versions, and mandatory
consumer versions. Rebuild new MDM from those inputs. Legacy rows may provide
comparison/crosswalk candidates but cannot substitute for source evidence.
For large sources run a bounded sample first, then the resumable full build.

## Catch-up, cutover and rollback rehearsal

1. Establish a baseline watermark and independent new-target checkpoints.
   Keep old MDM and old consumer contracts available for rollback.
2. Replay changes from baseline through the candidate watermark, proving
   source-family continuity. A missing interval requires a verified complete
   baseline and explicit new epoch, never silent catch-up completion.
3. Verify all mandatory consumer generations and reconcile missing/lost
   receipts. Freeze/recheck the final input and policy envelope before switch.
4. Rehearse consumer routing to the candidate generation; verify real API,
   Snowflake export and hosted graph behavior and exact completeness.
5. Rehearse rollback to the retained old system/consumer generation and replay
   its catch-up, including work arriving during the rehearsal. No destructive
   schema downgrade is a rollback strategy.
6. Present the immutable candidate evidence for the existing release gate.
   Activate only after it passes. Keep old MDM read-only for audit and in a
   demonstrably recoverable state for the agreed rollback window.

Before an actual switch, the release owner must settle the target identity,
consumer routing mechanism, acceptable pause/lag, legacy catch-up method,
rollback triggers and retention period. The window is currently unspecified;
do not invent one or delete old MDM. SEC capture, Snowflake silver and unrelated
analytics stay outside this migration.
