# 126: Ask OpenFIGI about the Securities known only from 13F

Priority: 126. Map: [Rebuild priorities](../map.md). From ticket 120's rulings
(operator, 2026-10-20 08:14 ET: "13F us cusip, first then if not use ticker",
then, 13F filing no ticker, "Ask by the filed FIGI (Recommended)").

Type: task. Status: open. Blocked by: the operator's permission for the
requests (a provider request needs it).

## What is known

- OpenFIGI was asked only for the CUSIPs and ISINs of the 2026 Q2 N-PORT
  data set. A Security known only from 13F has no OpenFIGI fields and no
  listings.
- 13F information tables carry a CUSIP and, on some rows, a FIGI; no ticker.
- No 13F capture is in the local captures today, so the count of 13F-only
  CUSIPs is not measured yet.

## Checklist

- [ ] Count the 13F-only CUSIPs (in 13F, not in N-PORT) and how many carry a filed FIGI, from a 13F capture
- [ ] Ask the operator's permission for the requests, with the counts and the request volume
- [ ] Ask by CUSIP (OpenFIGI `ID_CUSIP`); for those not found, by the filed FIGI (`ID_BB_GLOBAL`)
- [ ] The answers through OpenFIGI's own targets, as for N-PORT's identifiers
- [ ] Learning → skill (`security-master`, "Securities known only from 13F")
