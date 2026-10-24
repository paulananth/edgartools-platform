# Connect indexed records to shared matching and scope

Type: task
Status: claimed
Assignee: Codex
Claimed: 2026-10-23 19:37 ET
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: 01

## Question

Can the normal Merge Stage obtain all affected records through exact indexed portable reads?

## Parts

- [ ] Finish shared indexed scope, matching, correction, held-value and membership reads; validate immutable references, provenance and current-record freshness.
- [ ] Derive identifier namespaces, census/cascade paths and comparison selectors solely from pinned configuration; validate changed routes against retained latest readings.
- [ ] Prove invented sources, kinds, fields and namespaces, both arrival orders, corrections and unchanged replay; inspect actual bounded per-key plans beside populated unrelated records.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

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

## Qualification in progress

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
