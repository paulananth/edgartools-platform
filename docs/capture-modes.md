# Capture modes (normal vs strict_release)

Operator contract for dual-mode capture (ADR 0002 + Ticket 20 coexistence).
Code: `edgar_warehouse.infrastructure.capture_mode`.

## Modes

| Mode | Env | Bronze for edgartools-sourced SEC |
| --- | --- | --- |
| **normal** (default) | `WAREHOUSE_CAPTURE_MODE=normal` or unset | Only if `WAREHOUSE_PERSIST_BRONZE=1` (or explicit CLI persist) |
| **strict_release** | `WAREHOUSE_CAPTURE_MODE=strict_release` or `WAREHOUSE_RELEASE_MODE=1` | **Always** — evidence required for relationship bulk-load / release GO |

## Environment variables

| Variable | Meaning |
| --- | --- |
| `WAREHOUSE_CAPTURE_MODE` | `normal` \| `strict_release` |
| `WAREHOUSE_PERSIST_BRONZE` | Truthy → write bronze in **normal** mode |
| `WAREHOUSE_RELEASE_MODE` | Truthy → treat as **strict_release** if capture mode unset (legacy alias) |

## Non-edgartools sources

IAPD ADV bulk, PCAOB AuditorSearch bulk, operator FOIA drops, and any source
**not** obtained via edgartools **always** require immutable archive (bronze or
equivalent), in both modes. See `non_edgartools_source_requires_bronze()`.

## Silver system of engagement

Regardless of mode, re-runs should skip SEC network when silver already has
successful work at the current parser/facts version (tickets 03–05).
`strict_release` does not mean “re-download everything every time”; it means
**evidence must exist** when candidates are loaded for release proof.

## Metrics (ticket 02)

Capture runs emit `network_fetches` and `silver_skips` (and accession-level
variants) on the filing-artifact pipeline completion event and command metrics
so operators can prove a re-run did not reload SEC.

## Ticket references

Later ingest tickets (03–07) must call `resolve_capture_mode()` /
`should_persist_bronze()` instead of inventing new flags.
