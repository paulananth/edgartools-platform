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

## Filing document network gateway (ticket 06)

Filing documents and attachments use an **edgartools-only** network path
(`FILING_DOCUMENT_NETWORK_GATEWAY = "edgartools"` in
`bronze_filing_artifacts.py`). There is no parallel primary-document URL +
`sec_client.download_sec_bytes` fast path for this object class.

- Cache / silver skip still wins before network (existing attachments + raw objects).
- Missing edgartools content fails closed (`ParallelSecDownloadForbidden`); it does
  not fall back to raw HTTP.
- Bronze evidence writes remain available for `strict_release` / repair paths.

## Catalog + companyfacts gateway (ticket 07)

Tickers, submissions, daily index, and companyfacts SEC network I/O goes through
`edgar_warehouse.infrastructure.edgartools_sec_gateway` (edgartools HTTP), not
the parallel `sec_client` stack. Inventory:
`EDGARTOOLS_GATEWAY_OBJECT_CLASSES` (includes ticket 06 filing classes).

- Novelty-only catalog skips (ticket 05) and companyfacts version skip (ticket 04)
  still short-circuit before the gateway is called.
- Non-edgartools sources (`NON_EDGARTOOLS_OBJECT_CLASSES`: IAPD ADV bulk, PCAOB
  bulk, operator FOIA) remain mandatory-archive and are **not** claimed as
  edgartools-covered.

## Ticket references

Ingest tickets (03–07) must call `resolve_capture_mode()` /
`should_persist_bronze()` instead of inventing new flags.
