# Agent Decision Data Plane — issue index

Parent: [spec.md](./spec.md) · ADRs 0001/0002 · `docs/doctrine-data-plane.md`

All tickets: `Status: ready-for-agent` unless noted. Work the **frontier** (blockers done).

| # | Title | Blocked by |
|---|--------|------------|
| 01 | Dual-mode capture contract | — | **resolved** |
| 02 | Skip and network metrics | — | **resolved** |
| 03 | Silver-once ownership | 01, 02 | **resolved** |
| 04 | Silver-once companyfacts | 01, 02 | **resolved** |
| 05 | Catalog novelty-only refresh | 01, 02 | **resolved** |
| 06 | edgartools gateway filings | 01, 03 | **resolved** |
| 07 | edgartools gateway catalogs+facts | 04, 05, 06 | ready-for-agent |
| 08 | Snowflake export issuer evidence | — | **resolved** |
| 09 | Decision Watermark agent-grade | 08 | **resolved** |
| 10 | Subject Feature Screen | 09, 14 | ready-for-agent |
| 11 | Subject Bundle Read issuer | 09, 14 | ready-for-agent |
| 12 | Manager bundle ADV sections | 11 | ready-for-agent |
| 13 | SiS Agent View / Explore | 10, 11 | ready-for-agent |
| 14 | Universe single-writer | — | **resolved** |

**Frontier now:** 07 (unblocked by 04+05+06), 10 and 11 (unblocked by 09+14).

Do not start Ticket 20 bulk-load / strict ledger work from this index — separate workstream.
