# ISIN-only Securities link to their issuer

Priority: 102, tier 2. Map: [Rebuild priorities](../map.md).

Type: task (configuration). Status: open, not started. Blocked by: none. Deferred from: 22 (ISSUED_BY by issuer LEI), which linked the CUSIP Securities first.

## Question

The 35,309 ISIN-only N-PORT Securities (`sec.nport.security_isin.v1`) carry their filed issuer LEI but no ISSUED_BY link. Give them the same link by configuration (an issuer reduction keyed by ISIN, joined in `combine.yaml`, mapped as ticket 22 maps the CUSIP's), with the same one-LEI rule and the quarter's start (ticket 100).

## Checklist

- [ ] Configuration: ISIN issuer reduction, combine join, `relationships` on the ISIN contract
- [ ] Check on invented holdings through the chain and the Merge Stage; count on the real quarter against a direct count
- [ ] PR, CI green, merge on the operator's word
- [ ] Learning → skill
