# Connect indexed records to shared matching and scope

Type: task
Status: resolved
Assignee: Codex
Claimed: 2026-10-23 19:37 ET
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 01

## Question

Can the normal Merge Stage obtain all affected records through exact indexed portable reads?

## Parts

- [x] Finish shared indexed scope, matching, correction, held-value and membership reads; validate immutable references, provenance and current-record freshness. — 2026-10-23 20:28 ET; normal API cases, hostile references and current-pointer provenance pass on PostgreSQL/MySQL; final-code CI adapter jobs pass.
- [x] Derive identifier namespaces, census/cascade paths and comparison selectors solely from pinned configuration; validate changed routes against retained latest readings. — 2026-10-23 20:28 ET; invented kind/source/namespace/field routes and retained native route-reindex cases pass on both engines.
- [x] Prove invented sources, kinds, fields and namespaces, both arrival orders, corrections and unchanged replay; inspect actual bounded per-key plans beside populated unrelated records. — 2026-10-23 20:28 ET; 1,002 MDM tests; 46 affected cases plus installed smoke on PostgreSQL; MySQL normal/scope/lookup and installed cases pass; 17 bounded retained SQL Server helper/refusal checks pass; all three final-code CI adapter jobs pass.
- [x] Learning → skill: update its owning skill on a separate branch/PR, or record none. — 2026-10-23 20:28 ET; mdm-engineering/references/storage-adapters.md section “Qualify the normal read phase separately” in separate PR #1155; 80 focused skill tests pass.

## Acceptance evidence

Normal scope and matching return equivalent intended records on both engines without whole-table scans, hardcoded policy or a second merge algorithm.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.

## Initial design consult

The existing RecordReader and native record-history/index preparation are the
read boundary, qualified as helper paths in #1148. The normal proposal caller
still passes a PostgreSQL connection. Identifier-holder lookup, publication
times and relationship/review scope remain direct SQL calls. Connect a normal
read phase to this boundary and finish its missing operations; retain the
Store's refusal of unqualified MySQL writes until the atomic-merge ticket.

GoF: #1121, #1142 and #1148 show repeated transport changes across binding,
matching, corrections and scope. Extend the existing Adapter/RecordReader
facade and shared native index preparation. A second store hierarchy or merge
algorithm adds cost without solving indexed completeness or reference
validation. Keep the existing PostgreSQL persistence path until replacement
qualification and retirement account for it.

## Qualification log

- 2026-10-23 20:16 ET: 30 new read/scope cases pass on each of PostgreSQL
  and MySQL. After adding six pointer-provenance cases, the 21 scope cases
  plus ten retained lookup cases pass on each engine (31 each). The normal
  proposal/read API is exercised with an explicit read-only Store; normal
  MySQL mutation, assessments and publication remain refused.
- Retained SQL Server helper checks and normal-caller refusal are running;
  no SQL Server workflow support is claimed. Independent installed-bundle
  read-phase smoke checks follow a commit so they install the exact tree.
- Projection indexes and publication floors are prepared in shared Rust.
  Their integration into every normal save is ticket 04. Master/operator
  command portability is ticket 05; full installed workflow proof is 07.

## Review

### Standards

Invented records only; no provider or hosted calls, no migration changes.
The normal PostgreSQL persistence API remains in place. Read-only mutation
refusal is checked before admission; portable reads retain the destination
generation for its later authoritative save. Per-key group plans are checked
beside 2,000 unrelated entries, including actual PostgreSQL index conditions,
loops and row counts. No scan is accepted merely because it has an index name.

### Spec

The configured invented kind, sources, identifier and field routes pass both
arrival orders, held-value veto, corrections, quarantine/lift, publication
floors, source retirement and unchanged read/proposal replay. Relationship
scope keeps plain far ends stored and walks configured hierarchies whole.
Cross-group membership/candidate corruption and immutable/projection reference
corruption are refused. Full MySQL merge and operator commands remain later
tickets, rather than being inferred from read-phase qualification.

### GoF

The available gof-refactor-reviewer method was applied before code and to
this diff. History (#1121, #1148) shows transport changes across the same
matching/scope seam. Extend the existing RecordReader Adapter and MergeStage
facade; keep one shared calculation. The bounded native/portable transport
branches avoid a second class hierarchy. Their temporary debugging cost is
accepted until the normal writer qualifies and legacy callers retire. No
further pattern refactor is justified by current change costs.

## Resolution

Implementation: [PR #1156](https://github.com/paulananth/edgartools-platform/pull/1156).
Skill learning: [PR #1155](https://github.com/paulananth/edgartools-platform/pull/1155).
The read phase is implemented and qualified. These PRs still require all final
CI checks and named operator merge approval. No MySQL write or hosted activation
is authorized.

Local initial concurrent installation/helper attempts reached the 280-second
limit without reporting a failing case. Their disposable containers were
stopped. Reduced runs passed: installed read smoke on PostgreSQL (71.74 seconds)
and MySQL (16.65 seconds), MySQL scope/lookup checks (31 cases in 51.14
seconds), MySQL normal proposals (57.82 seconds), retained SQL
Server helpers/refusal (117.82 seconds). The final PostgreSQL affected run passed
46 cases in 267.00 seconds. CI also passes the complete adapter suites on the
implementation revision, including all new scope/reference cases.

### What remains

- Ticket 04 integrates all prepared lookup indexes/floors with the normal atomic
  save, assessments, history and publication intent. It must validate the observed
  generation at the destination; this read ticket alone cannot authorize writes.
- Ticket 05 ports operator correction worklists and master reads. This ticket
  supports correction inputs inside a normal proposal, not every operator command.
- Tickets 06–08 cover worker/publication recovery, full installed workflow
  qualification and active routine retirement. Historical migrations remain.
