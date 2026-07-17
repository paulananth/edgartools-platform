# 10 — Subject Feature Screen (issuer ranking)

**What to build:** A flat Subject Feature Screen over the Decision Subject Universe (warehouse active ∩ MDM active): Primary Annual FY and Latest Interim feature vectors, pure-SEC only, coverage flags, and watermark columns so an agent can rank/filter issuers without loading full neighborhoods.

**Blocked by:** 09 — Decision Watermark and Agent-Grade gate; 14 — Universe single-writer (preferred before claiming universe membership).

**Status:** resolved

- [x] Screen lists only Decision Subject Universe members
- [x] FY and interim vectors follow As-Of Decision Features rules (null ≠ zero; interim only when newer than FY)
- [x] Coverage flags present on factor sections
- [x] Results carry Decision Contract Version and Decision Watermark identity
- [x] No market price / PE fields
