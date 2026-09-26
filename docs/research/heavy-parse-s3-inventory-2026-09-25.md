# Heavy-parse S3 inventory

Date: 2026-09-25
Listed at: 2026-09-25T21:47:49Z
Bucket: `s3://edgartools-prod-bronze-690839588395/warehouse/bronze/`
Account: `690839588395`, `us-east-1`
Method: `ListObjectsV2` only. No object was downloaded.

The full selected-key file is `heavy-parse-s3-inventory-2026-09-25.jsonl` (17,259 rows). The 13F pin is `heavy-parse-s3-pin-13f-2026-09-25.json`.

## What survives for a 100 / 1,000 comparison

Only 13F information tables with an unambiguous file name.

| File name | Objects |
| --- | ---: |
| `infotable.xml` | 7,275 |
| `informationtable.xml` | 931 |
| `form13finfotable.xml` | 776 |
| **Pinned set** | **8,982** |

Those 8,982 objects are 2.0 GiB together. Sorted by size, then key:

- The 100 largest are 632 MiB. The biggest is 23.3 MB (`form13fInfoTable.xml`). The 100th is 2.4 MB.
- The 1,000 largest are 1.43 GiB. The 1,000th is 405 KB.

1.43 GiB is under the 20 GiB stop. A download of this pin is allowed. It has not been started.

`information_table.xml` is 506 more objects in the filename census. The underscore kept them out of the provisional tag (`informationtable` does not match `information_table`). They are not in the pin.

Another 8,249 keys merely contain `13f` in the file name (`13f.xml`, `d13fhr.txt`, quarterly names). Those are not treated as information tables. A `filing.xml` attachment cannot be classified from its name, and no body was read to classify it.

## Dropped

| Family | Objects | Why it is out |
| --- | ---: | --- |
| SEC companyfacts JSON | 0 | `warehouse/bronze/company_facts/` is empty. Nothing to pin. |
| GLEIF | 0 | `warehouse/bronze/gleif/` is empty. |
| ADV bulk CSV | 14 ZIPs, 111 MiB | `reference/iapd_adv_bulk/`, one ZIP per month from 2025-06 through 2026-06. Fewer than 100 files, so it is not a 100 / 1,000 artifact sample. `reference/adv_bulk_validation/` is the same 14 ZIPs again. |

## Counted, not selected

| Prefix | Objects | Bytes | What the large keys are |
| --- | ---: | ---: | --- |
| `filings/sec/` | 510,649 | 55.2 GiB | The 1,000 largest are 13.7 GiB and are XBRL ZIPs and proxy PDFs, not information tables. 28 objects are over 50 MB. |
| `submissions/sec/` | 204,345 | 13.8 GiB | Company submissions JSON. Largest is 4.5 MB. Not a parse-rule candidate in this pass. |
| `filing_artifact/` | 5,356 | 104 MiB | Content hashes, no file name. Largest is 1.0 MB. |

`filings/sec/` also holds the ownership files this pass is not migrating: `ownership.xml` 16,733, `form4.xml` 12,240, `doc4.xml` 3,430, `form3.xml` 679. HTML (`r1.htm` 18,640, `form8-k.htm`, `ex99-1.htm`) stays on the hand-written parsers.

## Next step at the time of this inventory

Download the pinned 13F keys once, then compare the current `parse_thirteenf` reader with a Source Contract XML reader on the 100 set. Start the 1,000 set only if those 100 match. Companyfacts stays out until those objects exist in bronze.

## Later work

The download and comparisons were subsequently reported by Grok in
[the comparison report](heavy-parse-compare-100-1000.md). The inventory
above records the earlier listing-only point in time. Codex check-in
verification is recorded separately in `.scratch/grok-takeover/heavy-parse-rules.md`.
