# 153: Reload the Security loads on current code

Priority: 153. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 17:24 ET, from [ticket 150](150-finish-the-security-loads-in-company-on.md).

Type: task. Status: open. Blocked by: none.

## Question

The 14 open OpenFIGI runs in `company-on` are pinned to worker code from 2026-10-29, which no current checkout can finish
(`load` reported all of them "pinned to other worker code" and started bundle 1 again in a new run). Finishing the
OpenFIGI Security load therefore means loading all 16 bundles again (about 25-35 min each, estimated from bundle 1's
request step: 301 of 512 units in 9 min). Does OpenFIGI need that reload, given 9 merges had already saved all their
batches and the masters exist, or is the result already equal? And the N-PORT Security 2026 Q2 load has not started.

## Parts

- [x] Count what `company-on` holds (2026-11-04 19:11 ET, read-only, counts only; the store's native MDM database): 0 Securities and 0 Security stage rows; masters are 12,937 fund structures, 2,433 Companies and 194 People; 77 saved batches, none of them OpenFIGI or N-PORT Security (sec.submissions.person 54, sec.nport.fund 13, gleif.level1 7, sec.nport.registrant 2, sec.submissions.company 1). So the question's premise ("masters exist") does not hold in this store: the reload is needed, not optional. Identifiers shared by more than one master: 839 lookup cross-references (820 N-PORT registrant CIKs shared by their fund structures, 15 series LEIs, 3 N-PORT LEIs and 1 SEC file number on Companies), all lookup only and none a Security; the `mdm` database of `company-on` and the other local store hold nothing
- [ ] The reload of the OpenFIGI bundles on current code, one bundle at a time, or the reason it is not needed
- [ ] The N-PORT Security load (2026 Q2)
- [ ] Counts; no identifier on two masters
- [ ] "Destination authority expired before save": measure one bundle that has never been merged, per batch (moved from 150)
- [ ] Learning → skill
