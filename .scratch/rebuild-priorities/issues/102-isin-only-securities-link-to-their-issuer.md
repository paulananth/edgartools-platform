# ISIN-only Securities link to their issuer

Priority: 102, tier 2. Map: [Rebuild priorities](../map.md).

Type: task (configuration). Status: done, merged (#1025, 2026-10-16 18:59 ET). Blocked by: none. Deferred from: 22 (ISSUED_BY by issuer LEI), which linked the CUSIP Securities first.

## Question

The 35,309 ISIN-only N-PORT Securities (`sec.nport.security_isin.v1`) carry their filed issuer LEI but no ISSUED_BY link. Give them the same link by configuration (an issuer reduction keyed by ISIN, joined in `combine.yaml`, mapped as ticket 22 maps the CUSIP's), with the same one-LEI rule and the quarter's start (ticket 100).

## Checklist

- [x] Configuration: ISIN issuer reduction, combine join, `relationships` on the ISIN contract: the issuer reading gains `isin_issuer` (no usable CUSIP, the ISIN from the `isin` pair set, the same LEI shape), `isin_issuers` in issuer-reduce.yaml, `isin_issuer` joined in combine.yaml, ISSUED_BY on `sec.nport.security_isin.v1`; Mapping Document regenerated; review (Standards, Spec, GoF) fixes applied (2026-10-16 18:50 ET)
- [x] Check on invented holdings through the chain and the Merge Stage; count on the real quarter against a direct count: `tests/integration/test_nport_isin_link.py` (one LEI links, starting at the quarter; two LEIs or none, no link; a holding with a CUSIP stays out; fails without the combine join). Real 2026q2 (`isin_issuer_run.py`, 7 min): 35,309 ISIN Securities accepted, 25,173 with one ISSUED_BY, all 36 batches dated 2026-06-30; the direct count agrees exactly (25,173 ISINs with one LEI, 101 with several, 0 differences) (2026-10-16 18:51 ET)
- [x] PR, CI green, merge on the operator's word: #1025, six checks green, merged by the operator 2026-10-16 18:59 ET
- [x] Learning → skill: none; the CUSIP path's lessons (ticket 22) cover it (2026-10-16 18:52 ET)
