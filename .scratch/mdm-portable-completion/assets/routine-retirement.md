# Governed store routine retirement

Baseline: merged main `43588ae7` (qualification #1178, skill learning #1179). Counts apply to a governed PostgreSQL owner installation, not a production store or an automatic import of populated legacy records.

## Before and after

| Surface | Before | After | Meaning |
|---|---:|---:|---|
| Historical migration files | 27 | 27 unchanged | Historical checksums and rollback evidence remain |
| New retirement migration files | 0 | 1 | Explicit governed owner installation applies 028 |
| Installed legacy-schema routines | 36 | 2 | 34 superseded routines removed without cascading drops |
| Latest legacy routine definition lines | 1,130 | 15 | Only immutable-row and configured-kind integrity guards remain |
| Retired routine definition lines | 0 | 1,115 | Installed executable definitions removed; source remains historical |
| Owner/store Python source lines in changed modules | 753 | 824 | Adds the owner retirement and readiness gate; does not claim Python deletion |

Generated PostgreSQL/MySQL storage capabilities remain active and retain authoritative transactions, freshness, uniqueness, fencing, immutable history and restricted grants. Those are outside the historical 36-routine inventory and are not retirement targets.

## Qualification

- Restricted PostgreSQL and MySQL owner/merge cohorts: 16 and 15 passing checks, including list identifiers, preview, rollback, repeat installation, interrupted owner recovery and unchanged replay.
- The three retirement cases per engine also pass after strengthening integrity checks: populated governed storage preserves its retained object and original replay receipt; PostgreSQL preserves every historical table's content and every constraint definition.
- PostgreSQL catalog matches exactly two retained integrity functions after retirement. Both immutable-ledger and disabled-kind refusals execute on the database; runtime retains no direct writes to historical MDM tables.
- An invented external SQL view prevents retirement. The entire DDL transaction rolls back, all 36 routines remain, no retirement checksum is saved, and the new normal caller refuses until the owner resolves the dependency and retries.
- A modified retirement file is refused against the retained checksum. No historical SQL file was changed.
- Final independently installed workflow and full CI are pending for this revision. Existing qualification establishes the predecessor, not a substitute for these checks.

## Remaining caller retirement

The default legacy PostgreSQL installation, its Python SQL fallback, and duplicated SQL calculation tests remain in this change. They must be removed in the next retirement slice, with explicit accounting for retained storage and historical-upgrade tests. The governed store already uses the qualified shared engine and never needs the removed routines. A populated legacy store is still refused by governed owner installation; conversion, hosted migration and activation remain separate gates.

## Review

### Standards

Own worktree and branch from current main. Guard passed; no historical SQL or unrelated work changed. Local checks use testmon, isolated databases, restricted roles, private diagnostics and deadlines under five minutes. Public artifacts contain counts and invented examples only.

### Spec

Implements the owner-retirement part of ticket 08. No full code-retirement completion is claimed: native caller deletion and its test disposition remain unchecked in the parent ticket. The new owner operation is explicit, retains data and integrity guards, and refuses unknown dependencies atomically.

### GoF

History shows the owner initialization boundary was extended by #1159 and #1171. Reuse its existing Store/Adapter seam and add one bounded owner operation before runtime admission. A second Store hierarchy or migration framework would increase review and recovery cost. No new pattern or policy interpreter is introduced.

Current caller/test retirement and final CI evidence are recorded in [caller retirement](caller-retirement.md); this document retains the earlier owner-retirement checkpoint.
