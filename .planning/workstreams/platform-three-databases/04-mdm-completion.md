# Complete configured MDM on PostgreSQL and MySQL

Operator direction from Lavish, 2026-10-23: implement MDM. Keep SQL Server
last, retain database authority, and introduce no entity/source policy in code.

- [x] Finish configured candidate routes and namespace selection through the normal PostgreSQL matching caller; preserve approved default outcomes — 979 MDM unit cases and 26 affected real-PostgreSQL cases passed; 2026-10-23 09:08 ET.
- [x] Install and qualify indexed candidate retrieval against populated PostgreSQL state — six invented-profile normal merge cases cover both routes, either arrival order, replay and held-value veto; populated migration preserves rows and pins; actual plans probe one key at a time beside 5,001 unrelated records; 2026-10-23 09:08 ET.
- [ ] Complete normal MySQL owner migration and restricted caller operations; helper storage qualification alone is insufficient.
- [ ] Qualify atomic merge, identity, history, relationships, detail lists and publication on both selected engines.
- [ ] Qualify competing/stale writers, rollback, interrupted recovery and unchanged replay on both engines.
- [ ] Qualify independently installed configured callers with invented vocabulary.
- [ ] Review Standards, Spec and GoF; resolve findings and publish evidence/PR.
- [ ] Learning → skill.

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
