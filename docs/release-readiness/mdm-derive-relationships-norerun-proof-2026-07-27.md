# MDM `derive-relationships` no-change rerun proof — 2026-07-27

This is a new, standalone evidence record. It does not edit or supersede any
2026-07-25 artifact (`ticket20-completion-2026-07-25.md`,
`ticket20-completion-evidence-2026-07-25.json`,
`ticket20-endpoint-seal-progress-2026-07-25.md`,
`ticket21-insider-coverage-10cik-2026-07-25.md`) or the 2026-07-26
`residual-holds-status-2026-07-26.md`.

## Purpose

Confirm `mdm derive-relationships` is idempotent: running it twice
back-to-back against prod, with identical input and no intervening state
change, produces zero new relationship identities on the second run.

## Preconditions verified before executing

| Check | Result |
| --- | --- |
| Step Functions running executions (`edgartools-*`) | none |
| ECS running tasks (`edgartools-prod-warehouse`, `edgartools-dev-warehouse`) | none |
| Baseline timestamp captured | `2026-07-27T20:44:27Z` |

## Runs executed

Both via `edgartools-prod-mdm-backfill-relationships`, input
`{"relationship_type":"EMPLOYED_BY","limit":100}` (maps to CLI
`mdm derive-relationships --relationship-type EMPLOYED_BY --target-per-type 100`).
`EMPLOYED_BY` was chosen over `HOLDS` because an overnight batch job was still
actively creating new `HOLDS` relationships as of `2026-07-27T02:01:12Z`
(`mdm_relationship_created` events observed), which would have confounded a
clean idempotency read; `EMPLOYED_BY` was quiet since its last clean run the
prior evening.

| Run | Execution name | ECS task | Start (UTC) | Result |
| --- | --- | --- | --- | --- |
| A | `task4-norerun-A-1785185072` | `612ac723b88341ddbb0668bf5045db55` | `2026-07-27T20:45:10.622726Z` | SUCCEEDED, exit 0 |
| B | `task4-norerun-B-1785185168` | `4022fe4b3d0f4ce9b8a76573b5bad0c2` | `2026-07-27T20:46:40.822994Z` | SUCCEEDED, exit 0 |

### Logged `mdm_progress` event, run A

```json
{"domain": "relationships", "existing": 28869, "inserted": 0, "rel_type": "EMPLOYED_BY", "target": 100, "total": 28869, "total_inserted": 0, "types_done": 1, "types_total": 1}
```

### Logged `mdm_progress` event, run B

```json
{"domain": "relationships", "existing": 28869, "inserted": 0, "rel_type": "EMPLOYED_BY", "target": 100, "total": 28869, "total_inserted": 0, "types_done": 1, "types_total": 1}
```

## Conclusion

Identical `existing` / `total` / `inserted` / `total_inserted` values across
both runs, both `inserted: 0`. **No-change rerun confirmed** — re-running
`derive-relationships` for `EMPLOYED_BY` with the same input produces zero
new relationship identities.

`EMPLOYED_BY`'s `active` count grew from 19,147 (per the `counts` snapshot at
`2026-07-26T23:39:24Z`, see `residual-holds-status-2026-07-26.md`) to 28,869
by the time of run A (`2026-07-27T20:45Z`). That growth happened between
those two timestamps, from unrelated derive activity (an overnight batch job
observed running through several relationship types, ending
`~2026-07-27T02:10Z`) — not from anything in this proof's two runs, which
were themselves back-to-back and produced zero inserts each.

Neither run invoked `sync-graph`, `verify-graph`, or `graph-activate`. This
proof is scoped to `derive-relationships` idempotency only; it does not
change graph state and does not touch the residual-holds candidate/active
generation decision recorded in `residual-holds-status-2026-07-26.md`
(candidate `residual-full-20260726T010010Z` remains verified but **not
activated**, per that document).
