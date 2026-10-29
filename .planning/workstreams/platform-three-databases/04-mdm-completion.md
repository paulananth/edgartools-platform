# Complete configured MDM on PostgreSQL and MySQL

Operator direction from Lavish, 2026-10-23: implement MDM. Keep SQL Server
last, retain database authority, and introduce no entity/source policy in code.

- [x] Finish configured candidate routes and namespace selection through the normal PostgreSQL matching caller; preserve approved default outcomes — 979 MDM unit cases and 26 affected real-PostgreSQL cases passed; 2026-10-23 09:08 ET.
- [x] Install and qualify indexed candidate retrieval against populated PostgreSQL state — six invented-profile normal merge cases cover both routes, either arrival order, replay and held-value veto; populated migration preserves rows and pins; actual plans probe one key at a time on a 5,001-row current store; 2026-10-23 09:08 ET.
- [x] Remove fixed candidate selectors from shared native record-index preparation; reindex from retained latest readings and refuse an unqualified route change without them — 994 MDM unit cases passed with the rebuilt native wheel; configured reindex/replay passed in the 24-case PostgreSQL and MySQL checkpoint cohorts; 2026-10-23 12:59 ET.
- [x] Add indexed current-record, candidate and membership transport with binding/correction readers against the shared native indexes; retain exact reference and provenance validation — 24 checkpoint cases per engine, including normal binding/correction module entry points, passed; this does not connect the complete Merge Stage caller; 2026-10-23 12:59 ET.
- [x] Qualify the destination-authority storage capability independently — PostgreSQL/MySQL commit expiry, overtaking, duplicate proof refresh, direct malformed requests, restricted rights, interrupted upgrade, indexed plans and unchanged historical fingerprints passed within each 24-case cohort; normal worker integration remains unchecked below; 2026-10-23 12:59 ET.
- [x] Close the demonstrated worker dependency: destination-local external resource fences and expiry must hold through the MySQL commit; preserve protocol 1–3 migration fingerprints and publication-on-input behavior. — 2026-10-28 20:12 ET: reconciled against merged tickets 02–08, #1210 current 20-check CI and 160 installed cases per engine; see ticket 09 closeout evidence.
- [x] Complete normal MySQL owner migration and restricted caller operations; helper storage qualification alone is insufficient. — 2026-10-28 20:12 ET: reconciled against merged tickets 02–08, #1210 current 20-check CI and 160 installed cases per engine; see ticket 09 closeout evidence.
- [x] Qualify atomic merge, identity, history, relationships, detail lists and publication on both selected engines. — 2026-10-28 20:12 ET: reconciled against merged tickets 02–08, #1210 current 20-check CI and 160 installed cases per engine; see ticket 09 closeout evidence.
- [x] Qualify competing/stale writers, rollback, interrupted recovery and unchanged replay on both engines. — 2026-10-28 20:12 ET: reconciled against merged tickets 02–08, #1210 current 20-check CI and 160 installed cases per engine; see ticket 09 closeout evidence.
- [x] Qualify the shipped candidate profile and registered migration files outside the checkout — independently installed five-wheel bundle from 48e406db; two checks passed in 182.37 seconds; 2026-10-23 09:13 ET.
- [x] Qualify independently installed normal merge callers on both engines with invented vocabulary. — 2026-10-28 20:12 ET: reconciled against merged tickets 02–08, #1210 current 20-check CI and 160 installed cases per engine; see ticket 09 closeout evidence.
- [x] Verify the checkpoint final CI head and review readiness — all nine checks green at 149ff418; operator-approved PR #1148 merged as 4b1bb68f after 994 unit, 49 PostgreSQL workflow, 98 adapter cases per PostgreSQL/MySQL, 88 retained SQL Server adapter and two independently installed bundle checks passed; 2026-10-23 13:23 ET.
- [x] Review the candidate-route checkpoint on Standards, Spec and GoF; publish evidence/PR — review below, clean whitespace/overlap checks and draft PR #1148 at implementation head 48e406db; 2026-10-23 09:13 ET.
- [x] Learning → skill: document protocol-4 destination authority, explicit input publication and pinned route reindexing with integration limits — separate skill PR #1150, seven genericity checks and all nine CI checks passed; operator-approved merge acd96aa8 verified; 2026-10-23 13:23 ET.

## Current MDM qualification

The normal configured PostgreSQL/MySQL MDM workflow is qualified through merged #1210: 20 checks, 160 independently installed cases per engine, two configured kinds and all 18 families. Historical checkpoint limitations below describe earlier revisions. SQL Server, broader Silver qualification, hosted migration and activation remain separate. The resolved closeout and its CI receipt are tracked in [ticket 09](../../../.scratch/mdm-portable-completion/issues/09-close-completion-and-skill-learning.md).

## Initial design review

Current main 9dfd4758 includes merged RDM completion (#1147) and learning
(#1146). No open PR overlaps MDM. This dedicated worktree starts there;
unrelated main and other runtimes remain preserved.

`matching.py` changed in #1121 and #1142, but candidate retrieval still uses
three fixed identifier/census expressions and a fixed namespace even when a
rule chooses a different comparison profile. That prevents the configured
comparison from reaching stored candidates. Reuse the existing pinned profile
and matching facade; derive its candidate selectors and owner-installed indexes
from the same declaration. No new policy registry or class hierarchy. The cost
is explicit index installation when the catalog gains a selector. MySQL's
normal Store remains separately unsupported until the full caller is qualified.

## PostgreSQL candidate-route checkpoint

The existing pair profile now supplies both retrieval and comparison. The
namespace, census entry path and cascade assignment path come from that
profile. Reviews, binding reasons and the held-identifier veto use its namespace.
Existing versioned primitive names remain compatible; no new policy is activated.

Migration 027 adds one generic index over current matching metadata, without
a duplicate candidate table, derived write protocol or per-source index DDL.
Identifiers reuse the existing generic identifier index. Each bound key is its
own lateral index probe. Containment is a candidate superset; exact scalar and
array-position checks prevent later census entries from entering a proposal.
The migration is transactional and leaves source readings, policy pins,
identities, batches, checkpoints and publication rows unchanged.

### Standards

Fresh branch/worktree from current main; no overlapping open PRs. Historical
migrations unchanged; fixtures and public evidence contain invented values or
counts only. Local test runs stay below five minutes. Restricted runtime writes
and all destination guards remain intact. `git diff --check` and overlap guard
pass. Independent installed-package qualification is next.

### Spec

Configuration reaches the real PostgreSQL Merge Stage, including waiting
records, both source orders and same-batch matching. The alternate profile works
while the old default remains selected. Its held-value veto refuses a different
identifier. This is a bounded PostgreSQL/configuration checkpoint, not completion
of MySQL's normal MDM migration/write workflow. Census production and remaining
cascade preparation still need their own configuration work.

### GoF

The resulting diff retains the matching facade, shared native comparison and
destination save authority. One profile replaces fixed record selectors in
retrieval; no class hierarchy, registry or second merge algorithm was added.
The cost is one generic metadata index and a required explicit owner migration.
Actual plans prove indexed probes on the populated store. Existing comparison,
correction and identity behavior remains protected by the affected tests.

## Final local checkpoint evidence

The complete MDM unit cohort passed 979 cases in 79.05 seconds. The two disjoint
PostgreSQL cohorts passed 26 cases in 27.81 seconds and 93 cases in 150.97 seconds
(119 total). Coverage retains correction/quarantine, identifier binding, atomic
save/rollback, competing generation/checkpoint writers, publication retry,
restricted grants, configured kinds and real lookup-index checks. All disposable
servers stopped when their cohort ended; retained test servers were not changed.

Implementation head 48e406db independently installed all five wheels. Two
outside-checkout checks passed in 182.37 seconds: an alternate candidate profile
reaches the shipped comparison and route selectors, and every registered migration
including 027 ships with publication preparation. This does not claim a complete
installed MySQL merge workflow. PR #1148 remains draft pending final CI.

The overall MDM ticket is **incomplete** while any part above remains unchecked.
SQL Server remains deferred until both first-priority engines are complete.


## Portable record-read and destination-authority checkpoint

The native lookup preparation now receives typed candidate routes from pinned
configuration. A route change rebuilds derived keys from the retained latest
reading, preserving the assertion, original batch and bronze provenance; it
refuses a changed route without that reading. RecordReader dereferences exact
immutable inputs and validates current source-record metadata and route pins.
Matching, binding and correction have indexed reader entry points; the complete
normal MySQL Store and Merge Stage are still unsupported.

Storage protocol 4, explicitly selected on PostgreSQL/MySQL only, adds optional
external destination-authority proofs outside the immutable business intent.
The destination checks monotonic fences, run/attempt ownership and expiry under
its transaction and again before completion. PostgreSQL also enforces expiry at
a caller-held commit; MySQL owns the commit and refuses an existing transaction.
SQL Server explicitly refuses protocol 4 while retaining its protocols 1–3.
Explicit publish_inputs distinguishes new immutable inputs that require a
publication from derived-index-only maintenance, which still creates no business
history or delivery. The nine historical engine/protocol fingerprints are frozen
and unchanged. Direct malformed requests are refused at the database itself.

### Standards

Existing WIP remains on its owning branch; no unrelated edits are included.
Public examples are invented. Real-engine cohorts use disposable isolated
servers and restricted runtime roles. Historical SQL and protocol fingerprints
remain unchanged; the new capability requires an explicit protocol upgrade.

### Spec

This checkpoint qualifies configured native selectors, indexed read transport
and required destination enforcement. It does not claim full normal MySQL
mastering, normal worker authority integration or PostgreSQL business-routine
retirement. Those remain unchecked and are decomposed in the separate Wayfinder
map. No source policy, acquisition, activation or deployment changes.

### GoF

History shows the existing skill-owned adapter and native record preparation
already carry this boundary (foundation changes #1073, #1096 and #1121). Retain
that adapter and shared computation. RecordReader collects exact pointer/input
transport without interpreting a second merge policy. No class hierarchy or
new merge algorithm is added; the cost is explicit derived-route reindexing and
qualification of the new storage protocol before normal worker integration.
