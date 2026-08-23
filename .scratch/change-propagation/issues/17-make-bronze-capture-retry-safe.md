# 17 — Make Bronze capture retry-safe and recoverable

**What to build:** Make the gated acquisition path converge safely across
retries, not-modified responses, source failures, worker loss, duplicate bytes,
and a failure between Bronze persistence and ledger finalization.

**Blocked by:** 15 — Capture one filing-artifact family through the gated Facade

**Status:** ready-for-agent

- [ ] Retries preserve the original decision, cause, observation position,
  request identity, and validators while using a new attempt and higher fence.
- [ ] `304` and same-bytes/same-producer observations link to prior verified
  evidence without creating a Logical Source Revision.
- [ ] Non-success responses remain Fetch Attempt evidence and cannot create a
  Bronze Artifact, source revision, Scope Completion, or retirement.
- [ ] An orphaned Bronze capture can attach only to its original existing Fetch
  Decision after checksum verification; otherwise it remains quarantined.
- [ ] A stale worker and a replayed message cannot overwrite or finalize work
  after a newer fenced attempt succeeds.
