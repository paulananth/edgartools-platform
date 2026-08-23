# Separate SEC source, Bronze evidence, PostgreSQL control, and Silver state authority

**Status:** accepted

**Supersedes:** the optional-Bronze, default network-skip, and parser-upgrade re-download decisions in [ADR 0002](0002-silver-soe-edgartools-exclusive.md)

**Preserves:** Silver as Runtime System of Engagement and `edgartools` as the exclusive SEC network gateway

SEC is the external source authority; Bronze is the mandatory immutable local evidence store for every successful response capable of affecting warehouse state; PostgreSQL is the sole local authority for acquisition and processing decisions; and Silver is the authoritative published business state used for lifecycle diffs. We chose these separate authorities so the platform can prove why each SEC request occurred, what exact bytes were captured, what was or was not processed, and which business state is current without letting S3 listings, workflow history, or downstream tables become competing ledgers.

## Consequences

- Every SEC request requires a prior PostgreSQL Source Fetch Decision, and new requests halt while the ledger is unavailable.
- A Logical Source Revision and processing eligibility require verified immutable Bronze evidence. Identical bytes may share one content-addressed object while retaining per-observation lineage.
- HTTP not-modified and non-success responses remain observation or attempt evidence and do not create source revisions; missing artifacts never prove retirement.
- PostgreSQL keeps separate fetch and processing lifecycles plus one joined operator status for every discovered candidate. Silver row state remains in Silver rather than being copied into the ledger.
- Parser, schema, contract, or configuration changes reprocess existing verified Bronze and redownload only when evidence is missing, corrupt, incomplete, or explicitly repaired.
- Every distinct newly captured Bronze Artifact is retained indefinitely, subject only to archival-tier transitions or explicit audited deletion. This prospective rule does not reconstruct or invalidate the completed deletion accepted by ADR 0005.
- Initial bootstrap and recovery after ledger loss require an operator-authorized Hybrid Source Baseline, complete non-serving Silver candidate, catch-up barrier, verification, and atomic activation in a new Ledger Epoch. Historical ledger decisions are not inferred from Bronze.
