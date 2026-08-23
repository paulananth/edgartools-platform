# 16 — Drive filing capture from SEC change discovery

**What to build:** Turn captured SEC change data into a sealed, auditable set
of filing candidates and drive each candidate through ledger-gated acquisition
without manual candidate construction.

**Blocked by:** 15 — Capture one filing-artifact family through the gated Facade

**Status:** ready-for-agent

- [ ] A captured SEC change observation produces a counted, ordered, digested
  Discovery Manifest for one bounded interval.
- [ ] Every in-universe candidate receives exactly one Fetch Decision tied to
  the discovery evidence and registry version.
- [ ] The interval cannot complete while any candidate is deferred, failed, or
  otherwise lacks an authorized terminal disposition.
- [ ] Replaying the same discovery evidence does not duplicate decisions,
  network requests, or logical source work.
- [ ] An end-to-end test proves a newly announced filing reaches verified
  Bronze while an unchanged or excluded candidate performs no download.
