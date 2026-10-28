# 146: Convert a populated native MDM store to governed storage

Priority: 146. Map: [Rebuild priorities](../map.md). Opened 2026-10-28 12:43 ET.

Type: task. Status: in progress (Claude, branch `claude/t146-mdm-data-migration`).
Blocked by: none. Unblocks ticket 120's switch-on in `company-on`.
Operator, 2026-10-28: "how to get Securities running in a store: build a data
migration so today's code can upgrade company-on - approved".

## Why

Since #1159 (2026-10-24) MDM installs governed storage (`mdm_store` tables,
protocol 6) and refuses a populated native store ("Populated native MDM requires a
qualified data migration; use a fresh prepared store"); #1190 retired the native
callers. Codex's PRs left the conversion out of scope; no plan exists for it.

## Found (2026-10-28 12:43 ET, `company-on`'s MDM, counts only)

Only the native layout (64 `mdm` tables; no `mdm_store`). Rows: 19,280 source
readings (and stage records), 15,564 masters (Company 2,433, Fund 12,937, Person
194), 15,789 decisions, all `bind` with their `entity_id`, 886 records set aside,
29,751 cross-references, 3 policies; no relationships, no detail versions.

## Design (advisor, 2026-10-28)

Replay, not a table-to-table copy: masters derive from source readings and
decisions. Read the native store's readings (revisions and times) and its bind
decisions, and apply them in order through today's Merge Stage (`apply(...,
decisions=...)`) into a new governed database on the same server, under today's
policy. Hard checks: the same master ids, the same binding per source record, no
decision lost, the readings set aside again. Differences from rule changes since
are counted by field, not failed. Never write the native database: build beside
it, verify, then swap names, keeping the native one for rollback. An owner-only,
resumable command beside `rebuild-name-index`; `migrate()`'s refusal stays.

## Parts

- [x] Inventory and design (2026-10-28 12:43 ET): above
- [ ] A replayed bind keeps its master id in a fresh governed store (the seam): test first
- [ ] GoF consult, then the command (owner-only, resumable, PostgreSQL)
- [ ] Tests: ids kept, bindings kept, set-aside records set aside, a second run changes nothing, the native database untouched
- [ ] Three-axis review, PR, CI green, merge
- [ ] Convert `company-on` (minutes at its size); counts against the inventory; the swap, with the native database kept
- [ ] Ticket 120's switch-on in `company-on`, and its loads (hours: say the time first)
- [ ] Learning → skill
