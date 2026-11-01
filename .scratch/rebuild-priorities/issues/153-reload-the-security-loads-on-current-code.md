# 153: Reload the Security loads on current code

Priority: 153. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 17:30 ET, from [ticket 150](150-finish-the-security-loads-in-company-on.md).

Type: task. Status: open. Blocked by: none.

## Question

The 14 open OpenFIGI runs in `company-on` are pinned to worker code from 2026-10-29, which no current checkout can finish
(`load` reported all of them "pinned to other worker code" and started bundle 1 again in a new run). Finishing the
OpenFIGI Security load therefore means loading all 16 bundles again (about 25-35 min each, estimated from bundle 1's
request step: 301 of 512 units in 9 min). Does OpenFIGI need that reload, given 9 merges had already saved all their
batches and the masters exist, or is the result already equal? And the N-PORT Security 2026 Q2 load has not started.

## Parts

- [ ] Count what `company-on` holds from the saved batches (Securities, identifiers on two masters) before any reload
- [ ] The reload of the OpenFIGI bundles on current code, one bundle at a time, or the reason it is not needed
- [ ] The N-PORT Security load (2026 Q2)
- [ ] Counts; no identifier on two masters
- [ ] "Destination authority expired before save": measure one bundle that has never been merged, per batch (moved from 150)
- [ ] Learning → skill
