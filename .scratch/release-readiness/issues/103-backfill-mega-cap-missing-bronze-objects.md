# 103 — Backfill 7 mega-cap CIKs' missing bronze objects

Type: task
Status: open

## Question

[Ticket 91](91-scan-other-ciks-for-missing-bronze-objects.md)'s scan (targeted
at rows fetched on the two suspect repair-script dates, 2026-07-25 and
2026-07-31) found that Apple is not the only affected CIK: 7 more mega-cap
issuers have `sec_raw_object` rows pointing at S3 keys that don't exist,
1,274 missing objects beyond Apple's already-known 494:

| CIK | Entity | Missing |
|---|---|---|
| 21344 | Coca-Cola Co | 753 |
| 1318605 | Tesla, Inc. | 125 |
| 789019 | Microsoft Corp | 203 |
| 1045810 | Nvidia Corp | 71 |
| 1067983 | Berkshire Hathaway Inc | 68 |
| 1018724 | Amazon.com Inc | 48 |
| 1652044 | Alphabet Inc. | 6 |

Same underlying gap as [Ticket 88](88-missing-s3-object-for-cached-accession-text-extraction.md):
DB rows reference bronze keys that were never actually written to S3, most
likely by the same one-off manual/repair scripts. Ticket 88's code fix
already makes this self-healing on next read (a cache-hit that finds the
object missing transparently re-fetches it) — this ticket, like Ticket 90,
is purely about closing the data gap proactively.

## Options

Same shape as Ticket 90's decision: (a) do nothing — Ticket 88's self-heal
closes the gap lazily; (b) a scoped `targeted-resync` per CIK (7 runs, one
per affected CIK, `--scope-type cik --scope-key <cik>`); (c) something
narrower, re-fetching only the known missing keys directly.

Worth checking before choosing: does `targeted-resync` support a multi-CIK
scope in one execution (would collapse 7 runs into 1), or must each CIK run
separately the way Ticket 90 does for Apple.

## Done when

An operator decision is made and, if a backfill is chosen, it's run and
verified for all 7 CIKs (re-diff each CIK's `sec_raw_object` storage paths
against a fresh S3 listing, expect 0 missing) — mirroring Ticket 90's own
verification method.
