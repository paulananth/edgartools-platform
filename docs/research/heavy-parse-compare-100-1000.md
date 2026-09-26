# 13F information table: rules reader against parse_thirteenf

Date: 2026-09-25
Pin: `heavy-parse-s3-pin-13f-2026-09-25.json`
Cache: `~/.local/share/edgartools/heavy-parse-13f/` (1,000 objects, downloaded once by ETag, no SEC requests)
Contract: `.scratch/source-contract/prototype/sources/thirteenf/contract.yaml`
Reader: the prototype Source Contract engine. One engine change: the `root` check compares the XML local name, so `{namespace}informationTable` matches `informationTable`.

The 100 set is the first 100 keys of the 1,000 set, both ordered by size descending. `period_of_report` is not in the information table, so `parse_thirteenf` was called with an empty period and did not apply the pre-Q4-2022 thousands multiplier. `security_class` is not in the contract. It depends on edgartools' ticker lookup.

Compared columns: CUSIP, issuer, class title, shares, market value, put/call, discretion, and the three voting amounts.

## 100

| | |
| --- | ---: |
| Files | 100 |
| Match | 100 |
| Row-count mismatches | 0 |
| Field mismatches | 0 |
| Both empty | 0 |
| Rows each side | 1,249,612 |
| Rules reader | 261.2 s |
| `parse_thirteenf` | 144.4 s |
| Peak RSS | 1.05 GB |

## 1,000, first pass

| | |
| --- | ---: |
| Files | 1,000 |
| Match | 989 |
| Row-count mismatches | 0 |
| Field mismatches | 11 |
| Rows each side | 2,955,223 |
| Rules reader | 821.3 s |
| `parse_thirteenf` | 540.1 s |

The 11 files disagreed in one place. `titleOfClass` was the literal text `None`. The rules reader kept that string. `parse_thirteenf` turns `none` and `nan` into null. The contract now uses the same blanking (`blank_missing_token@1`) on every text column.

## 1,000, after that blanking

| | |
| --- | ---: |
| Files | 1,000 |
| Match | 1,000 |
| Row-count mismatches | 0 |
| Field mismatches | 0 |
| Both empty | 0 |
| Rows each side | 2,955,223 |
| Rules reader | 648.5 s |
| `parse_thirteenf` | 358.7 s |
| Peak RSS | 1.08 GB |

## Rust, same pin

A release build (`rustc 1.98.1`, `quick-xml 0.37.5`) streams each information table and counts rows while accumulating selected values and a text hash. The clock excludes the file read, as the Python times do. Row counts match the Python run exactly. `security_class` and the ticker lookup are not in this timer.

| | Rows | Parse | File read |
| --- | ---: | ---: | ---: |
| 100 largest | 1,249,612 | 24.0 s | 0.6 s |
| 1,000 | 2,955,223 | 53.2 s | 2.2 s |

On the 1,000, that is about 6.7 times faster than `parse_thirteenf` (358.7 s) and about 12 times faster than the Python rules reader (648.5 s).

## Gate

The pinned rows match. The production writer stays `parse_thirteenf`. The rules reader is the prototype engine, and on this pin it took about 1.8 times as long. Switching silver over to it is a separate cutover, not something this match does by itself.

## Evidence limits and reproduction

The 100/1,000 results above are Grok's recorded measurements, preserved
at takeover. Raw per-run result files were not present in the source
worktree. They are not a new Codex acceptance run. The Python comparison
covers the ten listed columns only; it does not prove the reporting-period
multiplier, security classification, writer behavior, or MDM mastering.
The Rust prototype does not emit comparable rows, does not check voting
values or all XML text shapes (such as CDATA), and has no matched Python
hash. Its row counts and timings do not prove field equivalence; the
speed ratios compare unequal output work. Do not promote it from this
benchmark.

Both tools use local cached bytes; neither downloads bronze. ETags name
cache files, not a general integrity checksum. The current tools check
cached size against the pin; the takeover manifest preserves the pin's
SHA-256. Defaults are bounded to ten files. To reproduce a selected run:

```bash
uv run --extra mdm --extra s3 --with ruamel.yaml --with jsonschema python .scratch/source-contract/prototype/compare_thirteenf.py 10 --cache /path/to/cache
cargo run --release --locked --manifest-path .scratch/heavy-parse-rust/Cargo.toml -- 10 docs/research/heavy-parse-s3-pin-13f-2026-09-25.json /path/to/cache
```

The Source Contract selects business columns. It is a prototype mapping,
not the lossless shared parsed-record layer approved in ADR 0016. Production
parser or reader cutover requires its own implementation and acceptance.
