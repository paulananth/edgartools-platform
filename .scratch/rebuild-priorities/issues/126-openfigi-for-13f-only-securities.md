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

- [x] Count (2026-11-04 13:20 ET, counts only): the one 13F sample held locally has 29,942 CUSIPs, of which 20,311 pass their check digit (9,631 fail it); 10,033 of the valid ones are not in N-PORT's 385,382, and 3,229 of those carry a filed FIGI. The sample is not a whole quarter: a count over a whole 13F quarter needs a 13F capture, which is a provider download that needs permission
- [x] Permission asked (2026-11-04 13:20 ET): the operator answered "Sample few and report" (not the full 10,033). Volume asked for the full set: about 101 requests by CUSIP at 100 a request, then at most about 33 by FIGI
- [x] The sample sent (2026-11-04 13:20 ET, 2 requests with the operator's key, nothing else sent): 100 of the 13F-only CUSIPs chosen by a fixed seed, asked by CUSIP: 51 answered, 49 "No identifier found"; of the 49, 13 carry a filed FIGI, asked by FIGI: 4 answered. So 55 of 100 got an answer. Of the 51, the first listing is an exchange-traded product in 28, a common stock in 9, an ADR in 4, an open-end fund in 3, a US domestic corporate bond in 3 and a master limited partnership in 1. Answers kept privately, not committed
- [ ] Ask by CUSIP (OpenFIGI `ID_CUSIP`); for those not found, by the filed FIGI (`ID_BB_GLOBAL`)
- [ ] The answers through OpenFIGI's own targets, as for N-PORT's identifiers
- [ ] Learning → skill (`security-master`, "Securities known only from 13F")
