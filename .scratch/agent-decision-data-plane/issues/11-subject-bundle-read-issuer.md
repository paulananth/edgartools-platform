# 11 — Subject Bundle Read (issuer Trading-Relevant Neighborhood)

**What to build:** Single-subject Decision Graph Bundle for an issuer: Current Neighborhood (insiders with graph + gold source accessions, employment from proxy and Item 5.02, 13F dual sections holders_of_subject vs subject_as_manager_portfolio, auditor, optional parent when inventory complete), subject features, coverage flags, ADV not_applicable for pure issuers.

**Blocked by:** 09 — Decision Watermark and Agent-Grade gate; 14 — Universe single-writer.

**Status:** ready-for-agent

- [ ] Bundle root is Bundle Subject (CIK) with Decision Watermark and contract version
- [ ] Coverage flags distinguish present / empty / unavailable / not_applicable
- [ ] Insider section uses graph edges plus gold ownership rows for source accessions (not gold-only unresolved strings as agent-grade)
- [ ] 13F sections are separately named; lag metadata on Latest Complete Holdings Period
- [ ] EMPLOYED_BY sources distinguished; executive pay from gold proxy records
- [ ] AUDITED_BY prefers auditor evidence identity rules; HAS_PARENT optional with honest scope
- [ ] Pure issuer bundles do not require ADV
