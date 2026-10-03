# Updated YAML 13F corpus rerun

The corrected `prototype-2` YAML contract reproduces every prior output hash on the same 100 distinct filings (166,295,070 bytes, 331,039 rows). Native Rust and the Python facade accept all 100 and produce identical complete tables. The facade uses an empty custom-step registry.

## Five-trial results

| Mode | Workers | Prior median | New median | New range | Max peak RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| hybrid | 1 | 20.21s | 19.61s | 17.96–34.52s | 418.1 MiB |
| hybrid | 2 | 22.77s | 14.02s | 13.29–23.18s | 499.6 MiB |
| native | 1 | 17.07s | 25.49s | 20.43–30.62s | 390.4 MiB |
| native | 2 | 12.06s | 15.37s | 11.85–23.58s | 467.4 MiB |
| native | 4 | 9.74s | 17.29s | 10.72–21.00s | 640.7 MiB |

Timing includes warm cached file reads, complete configured in-memory output, and output disposal. Five passes per mode ran in fresh processes with rotated mode order; RSS includes setup and warm-up. Acquisition and downstream writers/mastering are excluded.

## Interpretation

The hybrid two-worker median improves from 22.77s to 14.02s (38.4% shorter), consistent with removing Python callbacks. This is an observed comparison across separate runs, not an isolated causal measurement. The native two-worker median is 15.37s, about 9.7% slower than hybrid two workers in this run. Native four workers have a 17.29s median and higher memory usage. This rerun does not demonstrate a native Rust throughput advantage.

The machine was busy: a process snapshot during trial two showed the VM using about 132% CPU, Ghostty about 39%, and WindowServer about 30%. Wide timing ranges and uneven contention limit both cross-run comparisons and small differences between modes. The prior contract benchmark used callbacks; its native adoption recommendation needs qualification with the current declarative contract on a quiet host. Correctness is confirmed here.

## Regression caught and corrected

Comparing native and facade results alone missed a shared YAML typo: `share_type` used `shrsOrPrnamt` instead of `shrsOrPrnAmt`. Comparing against prior output hashes exposed the lost field. The path is corrected and the existing native fixture test now asserts `share_type == "SH"`; all five 13F Rust tests pass. The corrected corpus has identical prior outputs on every filing. The interrupted run is preserved under `invalid-path-run/` and excluded from the table.

The corrected full run took 564.3 seconds (9 minutes 24 seconds). The additional interrupted run and investigation lengthened the overall task. No network, database or object-storage requests were performed by the corpus runner.

## Evidence

- [Raw timings](../../.planning/workstreams/rust-parser-yaml-rerun/benchmark.json)
- [Public input manifest and hashes](../../.planning/workstreams/rust-parser-yaml-rerun/corpus-manifest.public.json)
- [Complete parity and output hashes](../../.planning/workstreams/rust-parser-yaml-rerun/corpus-parity.json)
- [Provenance](../../.planning/workstreams/rust-parser-yaml-rerun/provenance.json)

Contract SHA256: `710d928ed769c73f9f66831043e5fbdc7b18c4a3ee7610ddcbd493cdaed9fa7b`.
